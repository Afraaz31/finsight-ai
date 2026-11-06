"""Level 4 tests: file validation, extraction, table cleaning, safe calculations, upload routing.

No internet, no API key, no quota: the LLM, the embedding model and ChromaDB are replaced by fakes.
Uses the fictional sample files in samples/.
"""
from pathlib import Path

import pandas as pd
import pytest

from backend.services import document_qa_service, upload_service
from backend.services.table_service import (PlanError, clean_number, execute_plan, parse_plan,
                                            prepare_table)
from backend.services.upload_service import UploadError, validate

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
needs_samples = pytest.mark.skipif(not SAMPLES.exists(), reason="samples/ folder missing")


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Uploads go to a temporary folder, and text indexing is faked (no model, no ChromaDB)."""
    monkeypatch.setattr(upload_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(upload_service, "_index_text", lambda doc_id, filename, pages: len(pages))
    return tmp_path / "uploads"


# ---------- validation ----------
@pytest.mark.parametrize("filename, data, message", [
    ("report.xlsm", b"PK\x03\x04data", "not accepted"),     # macro workbook
    ("virus.exe", b"MZ", "not accepted"),
    ("notes.rtf", b"{\\rtf", "Unsupported file type"),
    ("fake.pdf", b"hello", "not a real PDF"),               # wrong content for the extension
    ("fake.xlsx", b"hello", "not a real .xlsx"),
    ("empty.csv", b"", "empty"),
])
def test_validate_rejects_bad_files(filename, data, message):
    with pytest.raises(UploadError, match=message):
        validate(filename, data)


def test_validate_rejects_too_big(monkeypatch):
    monkeypatch.setattr(upload_service, "MAX_UPLOAD_MB", 1)
    with pytest.raises(UploadError, match="limit"):
        validate("big.csv", b"a" * (2 * 1024 * 1024))


def test_validate_accepts_good_csv():
    assert validate("Data.CSV", b"Year,Revenue\n2025,10") == ".csv"


# ---------- extraction ----------
@needs_samples
def test_text_pdf_is_extracted_page_by_page():
    pages = upload_service.extract_pdf((SAMPLES / "kestrel_annual_report.pdf").read_bytes())
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert "441.2" in pages[1]["text"]


@needs_samples
def test_scanned_pdf_is_refused():
    with pytest.raises(UploadError, match="scanned"):
        upload_service.extract_pdf((SAMPLES / "scanned_invoice.pdf").read_bytes())


# ---------- table cleaning ----------
@pytest.mark.parametrize("raw, expected", [
    ("$1,234.5", 1234.5), ("(500)", -500.0), ("12.5%", 12.5), ("-7", -7.0), (42, 42.0)])
def test_clean_number(raw, expected):
    assert clean_number(raw) == expected


def test_clean_number_not_a_number():
    assert clean_number("Revenue") is None
    assert pd.isna(clean_number("—"))


def test_wide_table_becomes_long():
    wide = pd.DataFrame({"Line Item": ["Revenue", "Net Income"], "FY2024": ["$100", "$10"],
                         "FY2025": ["$120", "(5)"]})
    long, reshaped = prepare_table(wide)
    assert reshaped is True
    assert list(long.columns) == ["Line Item", "Period", "Value"]
    loss = long[(long["Line Item"] == "Net Income") & (long["Period"] == 2025)]["Value"].iloc[0]
    assert loss == -5.0


@needs_samples
def test_excel_title_row_is_skipped():
    sheets = upload_service.extract_tables(".xlsx", (SAMPLES / "kestrel_statements.xlsx").read_bytes())
    df, _ = prepare_table(sheets[0][1])
    assert "Line Item" in df.columns            # the real header, not the title row


# ---------- safe calculations ----------
@pytest.fixture
def yearly():
    return pd.DataFrame({"Year": [2023, 2024, 2025], "Revenue": [352.4, 398.7, 441.2],
                         "Net Income": [41.8, 52.3, 61.9]})


def test_sum_and_filter(yearly):
    result = execute_plan(yearly, {"operation": "sum", "column": "revenue",
                                   "filters": [{"column": "Year", "op": ">=", "value": "2024"}]})
    assert "839.90" in result["summary"]       # 398.7 + 441.2, exact


def test_growth(yearly):
    table = execute_plan(yearly, {"operation": "growth", "column": "Revenue", "order_by": "Year"})["table"]
    assert table["change_%"].iloc[-1] == pytest.approx(10.66, abs=0.01)


def test_ratio_is_margin(yearly):
    table = execute_plan(yearly, {"operation": "ratio", "numerator": {"column": "Net Income"},
                                  "denominator": {"column": "Revenue"}, "group_by": "Year"})["table"]
    assert table["ratio_%"].iloc[-1] == pytest.approx(14.03, abs=0.01)


def test_unknown_column_gives_helpful_error(yearly):
    with pytest.raises(PlanError, match="Available columns"):
        execute_plan(yearly, {"operation": "sum", "column": "Profit"})


def test_unknown_operation_is_refused(yearly):
    with pytest.raises(PlanError, match="Unsupported operation"):
        execute_plan(yearly, {"operation": "exec", "column": "Revenue"})


def test_parse_plan_handles_code_fences():
    assert parse_plan('```json\n{"operation": "sum", "column": "Revenue"}\n```')["operation"] == "sum"
    with pytest.raises(PlanError):
        parse_plan("Sorry, I can't do that.")


# ---------- storing and routing ----------
@needs_samples
def test_add_list_delete_table_upload(upload_dir):
    meta = upload_service.add_upload("kestrel_financials.csv",
                                     (SAMPLES / "kestrel_financials.csv").read_bytes())
    assert meta["kind"] == "table" and meta["tables"][0]["rows"] == 4
    assert [m["doc_id"] for m in upload_service.list_uploads()] == [meta["doc_id"]]
    df, sheet = upload_service.load_table(meta["doc_id"])
    assert df["Revenue"].sum() == pytest.approx(1502.3)
    upload_service.delete_upload(meta["doc_id"])
    assert upload_service.list_uploads() == []


@needs_samples
def test_failed_upload_leaves_nothing_behind(upload_dir):
    with pytest.raises(UploadError):
        upload_service.add_upload("scanned_invoice.pdf", (SAMPLES / "scanned_invoice.pdf").read_bytes())
    assert not upload_dir.exists() or not any(upload_dir.iterdir())


def test_doc_id_cannot_escape_the_upload_folder(upload_dir):
    with pytest.raises(UploadError):
        upload_service.get_upload("../../.env")


@needs_samples
def test_table_question_uses_python_numbers(upload_dir, monkeypatch):
    meta = upload_service.add_upload("kestrel_financials.csv",
                                     (SAMPLES / "kestrel_financials.csv").read_bytes())
    seen = {}

    def fake_llm(system, user):
        if system.startswith("You convert"):
            return '{"operation": "sum", "column": "Revenue"}', "fake"
        seen["explain_prompt"] = user
        return "Total revenue is 1,502.30 in the file's units.", "fake"

    monkeypatch.setattr("backend.services.table_service.generate_answer", fake_llm)
    result = document_qa_service.answer_upload_question("What is total revenue?", [meta["doc_id"]])
    assert "1,502.30" in seen["explain_prompt"]          # Python's number was given to the LLM
    assert result["calculation"]["plan"]["operation"] == "sum"
    assert result["sources"][0]["filename"] == "kestrel_financials.csv"


def test_mixing_table_and_text_is_refused(upload_dir, monkeypatch):
    fake = {"a1": {"doc_id": "a1", "kind": "table", "filename": "t.csv"},
            "b2": {"doc_id": "b2", "kind": "text", "filename": "r.pdf", "chunks": 3}}
    monkeypatch.setattr(document_qa_service, "get_upload", lambda d: fake[d])
    with pytest.raises(UploadError, match="one table at a time"):
        document_qa_service.answer_upload_question("compare", ["a1", "b2"])
