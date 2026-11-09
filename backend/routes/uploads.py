"""Upload endpoints: add, list, ask, delete. Routes stay thin; the services do the work."""
import math

from fastapi import APIRouter, File, Response, UploadFile, status

from backend.config import MAX_UPLOAD_MB
from backend.routes import _guarded
from backend.schemas.api_schemas import UploadAnswer, UploadAskRequest, UploadMeta
from backend.services.document_qa_service import answer_upload_question
from backend.services.upload_service import (UploadError, add_upload, delete_upload, get_upload,
                                             list_uploads)

router = APIRouter(prefix="/uploads", tags=["uploads"])


def json_safe(value):
    """JSON has no NaN/Infinity (e.g. the first row of a growth table). Replace them with null."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


@router.post("", response_model=UploadMeta, status_code=status.HTTP_201_CREATED)
def upload(file: UploadFile = File(..., description="PDF, TXT, DOCX, CSV or XLSX, max 10 MB")) -> dict:
    """Upload one file. Returns its doc_id, which you use to ask questions about it."""
    data = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)   # read at most limit+1 bytes
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"The file is larger than {MAX_UPLOAD_MB} MB.")
    return add_upload(file.filename or "upload", data)


@router.get("", response_model=list[UploadMeta])
def uploads() -> list[dict]:
    """All uploaded files, newest first."""
    return list_uploads()


@router.get("/{doc_id}", response_model=UploadMeta)
def upload_details(doc_id: str) -> dict:
    return get_upload(doc_id)


@router.post("/ask", response_model=UploadAnswer)
def ask(request: UploadAskRequest) -> dict:
    """Question about one table, or one or more text documents."""
    _guarded.before(request.question)
    result = answer_upload_question(request.question, request.doc_ids, sheet=request.sheet,
                                    use_cache=request.use_cache)
    return json_safe(_guarded.after({**result, "route": "upload"}))


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(doc_id: str) -> Response:
    delete_upload(doc_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
