"""Document Agent: answers questions about PDF / Word / TXT files using RAG.

Its job: search the chosen documents (each one separately, never mixed with SEC data), number the
passages [1], [2] ..., and either write its own cited answer or hand the passages to the Orchestrator.
"""
from backend.services import number_guard
from backend.services.document_qa_service import (UPLOAD_SYSTEM_PROMPT, _cited_sources, build_upload_context,
                                                  retrieve_from_uploads)
from backend.services.llm_service import generate_answer

NAME = "Document Agent"


def run(task: str, metas: list[dict], write_answer: bool = True) -> dict:
    hits = retrieve_from_uploads(task, metas)
    base = {"agent": NAME, "task": task, "files": [m["filename"] for m in metas], "hits": hits,
            "model": None, "errors": []}
    if not hits:
        return {**base, "answer": "I couldn't find anything relevant in the document(s).", "evidence": "",
                "sources": [], "errors": ["no relevant passages found"]}
    context = build_upload_context(hits)
    if not write_answer:      # the Orchestrator will write the answer and cite these passages
        return {**base, "answer": None, "evidence": context, "sources": []}
    answer, model = generate_answer(UPLOAD_SYSTEM_PROMPT, f"SOURCES:\n\n{context}\n\n---\nQUESTION: {task}\n\n"
                                                          "Answer using only the sources above.")
    answer = number_guard.drop_unknown_citations(answer, len(hits))   # no citation that leads nowhere
    return {**base, "answer": answer, "model": model, "evidence": context, "sources": _cited_sources(hits, answer)}
