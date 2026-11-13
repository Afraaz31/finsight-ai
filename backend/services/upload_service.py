"""Level 4: accept a user's file, check it, extract its content, and store it.

Text files (PDF, TXT, DOCX) -> pages of text -> chunks -> embeddings -> ChromaDB 'user_uploads'
Table files (CSV, XLSX)     -> cleaned Pandas tables saved as CSV (for exact maths later)

Every upload gets its own doc_id and folder:  data/uploads/<doc_id>/
    original.<ext>   the file exactly as uploaded
    meta.json        what we know about it (name, kind, pages/sheets, chunk count)
    table_<n>.csv    (tables only) the cleaned tables
"""
import io
import json
import logging
import shutil
import time
import uuid

import pandas as pd

from backend.config import (MAX_UPLOAD_MB, TABLE_EXTENSIONS, TEXT_EXTENSIONS, UPLOAD_COLLECTION,
                            UPLOAD_DIR)
from backend.services.embedding_service import embed_texts
from backend.services.retrieval_service import get_or_create_collection
from backend.services.table_service import prepare_table
from ingestion.chunk_documents import chunk_text

log = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = 30      # less than this on average -> probably a scanned (image) PDF
ZIP_MAGIC, PDF_MAGIC = b"PK\x03\x04", b"%PDF"
BLOCKED_EXTENSIONS = {".xlsm", ".xlsb", ".xls", ".docm", ".exe", ".bat", ".js", ".py", ".zip"}


class UploadError(Exception):
    """A problem with the uploaded file. The message is safe to show to the user."""


class UploadNotFound(UploadError):
    """No upload with that doc_id (the API turns this into HTTP 404)."""


# ---------- 1. Validate ----------
def validate(filename: str, data: bytes) -> str:
    """Check name, size and real content type. Returns the lower-case extension."""
    name = (filename or "").strip()
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext in BLOCKED_EXTENSIONS:
        raise UploadError(f"'{ext}' files are not accepted (macros or programs are never opened). "
                          "Save the file as .xlsx / .docx / .pdf / .csv / .txt.")
    if ext not in TEXT_EXTENSIONS | TABLE_EXTENSIONS:
        raise UploadError(f"Unsupported file type '{ext or 'none'}'. "
                          f"Allowed: {', '.join(sorted(TEXT_EXTENSIONS | TABLE_EXTENSIONS))}")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"The file is {len(data) / 1_048_576:.1f} MB. The limit is {MAX_UPLOAD_MB} MB.")
    # The extension can lie; the first bytes of the file can't.
    if ext == ".pdf" and not data.startswith(PDF_MAGIC):
        raise UploadError("This file is named .pdf but is not a real PDF.")
    if ext in {".xlsx", ".docx"} and not data.startswith(ZIP_MAGIC):
        raise UploadError(f"This file is named {ext} but is not a real {ext} file.")
    return ext


# ---------- 2. Extract ----------
def extract_pdf(data: bytes) -> list[dict]:
    """PDF -> [{"page": 1, "text": ...}, ...]. Refuses encrypted or scanned (image-only) PDFs."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise UploadError(f"The PDF could not be read: {exc}") from exc
    if reader.is_encrypted:
        raise UploadError("The PDF is password-protected. Upload an unlocked copy.")
    pages = [{"page": i, "text": (page.extract_text() or "").strip()}
             for i, page in enumerate(reader.pages, 1)]
    total = sum(len(p["text"]) for p in pages)
    if not pages or total / len(pages) < MIN_CHARS_PER_PAGE:
        raise UploadError("This PDF has almost no readable text. It is probably a scanned image. "
                          "FinSight does not do OCR, so it can't read it. Upload a text-based PDF.")
    return [p for p in pages if p["text"]]


def extract_txt(data: bytes) -> list[dict]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text.strip():
        raise UploadError("The text file has no content.")
    return [{"page": 1, "text": text.strip()}]


def extract_docx(data: bytes) -> list[dict]:
    """Word file -> paragraphs and tables as text (python-docx never runs macros)."""
    from docx import Document
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise UploadError(f"The Word file could not be read: {exc}") from exc
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    if not parts:
        raise UploadError("The Word file has no readable text.")
    return [{"page": 1, "text": "\n".join(parts)}]


def extract_tables(ext: str, data: bytes) -> list[tuple[str, pd.DataFrame]]:
    """CSV/XLSX -> [(sheet_name, raw DataFrame)]. openpyxl reads values only, never macros."""
    try:
        if ext == ".csv":
            return [("csv", pd.read_csv(io.BytesIO(data)))]
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, engine="openpyxl")
        return list(sheets.items())
    except Exception as exc:
        raise UploadError(f"The table could not be read: {exc}") from exc


# ---------- 3. Store ----------
def _index_text(doc_id: str, filename: str, pages: list[dict]) -> int:
    """Chunk + embed + store text in the uploads collection. Returns the number of chunks."""
    ids, texts, metas = [], [], []
    for page in pages:
        for i, body in enumerate(chunk_text(page["text"])):
            ids.append(f"{doc_id}_p{page['page']}_{i:04d}")
            texts.append(f"{filename} | page {page['page']}\n{body}")
            metas.append({"source_type": "upload", "doc_id": doc_id, "filename": filename,
                          "page": page["page"], "chunk_index": i})
    collection = get_or_create_collection(UPLOAD_COLLECTION)
    for start in range(0, len(ids), 256):
        end = start + 256
        collection.upsert(ids=ids[start:end], documents=texts[start:end],
                          metadatas=metas[start:end], embeddings=embed_texts(texts[start:end]))
    return len(ids)


def add_upload(filename: str, data: bytes) -> dict:
    """Validate, extract and store one file. Returns its meta (doc_id, kind, ...)."""
    ext = validate(filename, data)
    doc_id = uuid.uuid4().hex[:12]
    folder = UPLOAD_DIR / doc_id
    meta = {"doc_id": doc_id, "filename": filename, "extension": ext, "size_bytes": len(data),
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if ext in TEXT_EXTENSIONS:
            extractor = {".pdf": extract_pdf, ".txt": extract_txt, ".docx": extract_docx}[ext]
            pages = extractor(data)
            folder.mkdir(parents=True)
            meta.update(kind="text", pages=len(pages), characters=sum(len(p["text"]) for p in pages))
            meta["chunks"] = _index_text(doc_id, filename, pages)
        else:
            raw_tables = extract_tables(ext, data)
            folder.mkdir(parents=True)
            tables = []
            for n, (sheet, raw) in enumerate(raw_tables):
                df, reshaped = prepare_table(raw)
                if df.empty:
                    continue
                csv_name = f"table_{n}.csv"
                df.to_csv(folder / csv_name, index=False)
                tables.append({"sheet": str(sheet), "file": csv_name, "rows": len(df),
                               "columns": list(df.columns), "reshaped_to_long": reshaped})
            if not tables:
                raise UploadError("No data rows were found in the table.")
            meta.update(kind="table", tables=tables)
        (folder / f"original{ext}").write_bytes(data)
        (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)   # never leave a half-stored upload behind
        raise
    log.info("Stored upload %s (%s, %s)", doc_id, filename, meta["kind"])
    return meta


# ---------- 4. Find / load / delete ----------
def list_uploads() -> list[dict]:
    if not UPLOAD_DIR.exists():
        return []
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in UPLOAD_DIR.glob("*/meta.json")]
    return sorted(metas, key=lambda m: m["uploaded_at"], reverse=True)


def get_upload(doc_id: str) -> dict:
    path = UPLOAD_DIR / doc_id / "meta.json"
    if not doc_id.isalnum() or not path.exists():      # isalnum blocks paths like "../.."
        raise UploadNotFound(f"No uploaded document with id '{doc_id}'.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_table(doc_id: str, sheet: str | None = None) -> tuple[pd.DataFrame, str]:
    """Load a cleaned table of an upload (first sheet unless `sheet` is given)."""
    meta = get_upload(doc_id)
    if meta["kind"] != "table":
        raise UploadError(f"'{meta['filename']}' is a text document, not a table.")
    tables = meta["tables"]
    chosen = next((t for t in tables if sheet and t["sheet"].lower() == sheet.lower()), tables[0])
    return pd.read_csv(UPLOAD_DIR / doc_id / chosen["file"]), chosen["sheet"]


def delete_upload(doc_id: str) -> None:
    meta = get_upload(doc_id)
    if meta["kind"] == "text":
        get_or_create_collection(UPLOAD_COLLECTION).delete(where={"doc_id": doc_id})
    shutil.rmtree(UPLOAD_DIR / doc_id)
    log.info("Deleted upload %s (%s)", doc_id, meta["filename"])
