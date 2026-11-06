"""Quota Shield tests: model fallback, Gemma prompt handling, Ollama backup, cache, cited-only sources.

Gemini, Ollama and search are all fakes: no internet, no API key, no quota used.
"""
import pytest
from google.genai import errors

from backend.services import cache_service, llm_service, rag_service


# ---------- fakes ----------
class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    """Pretends to be client.models. `plan` maps model name -> error code or answer text."""

    def __init__(self, plan):
        self.plan, self.calls = plan, []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents,
                           "system": config.system_instruction})
        outcome = self.plan[model]
        if isinstance(outcome, int):
            cls = errors.ServerError if outcome >= 500 else errors.ClientError
            raise cls(outcome, {"error": {"code": outcome, "message": "fake", "status": "FAKE"}})
        return FakeResponse(outcome)


class FakeClient:
    def __init__(self, plan):
        self.models = FakeModels(plan)


@pytest.fixture
def chain(monkeypatch):
    """Use a fixed 3-model chain and Ollama off, whatever is in your .env."""
    monkeypatch.setattr(llm_service, "GEMINI_MODEL", "main-flash-lite")
    monkeypatch.setattr(llm_service, "GEMINI_FALLBACK_MODELS", ["backup-flash-lite", "gemma-4-31b-it"])
    monkeypatch.setattr(llm_service, "OLLAMA_ENABLED", False)

    def install(plan):
        client = FakeClient(plan)
        monkeypatch.setattr(llm_service, "_client", client)
        return client.models
    return install


# ---------- fallback chain ----------
def test_main_model_answers_first(chain):
    models = chain({"main-flash-lite": "ok", "backup-flash-lite": "no", "gemma-4-31b-it": "no"})
    assert llm_service.generate_answer("rules", "q") == ("ok", "main-flash-lite")
    assert [c["model"] for c in models.calls] == ["main-flash-lite"]


def test_quota_error_falls_back_to_next_model(chain):
    models = chain({"main-flash-lite": 429, "backup-flash-lite": 503, "gemma-4-31b-it": "gemma ok"})
    assert llm_service.generate_answer("rules", "q") == ("gemma ok", "gemma-4-31b-it")
    assert [c["model"] for c in models.calls] == ["main-flash-lite", "backup-flash-lite", "gemma-4-31b-it"]


def test_bad_key_stops_immediately(chain):
    models = chain({"main-flash-lite": 403, "backup-flash-lite": "never", "gemma-4-31b-it": "never"})
    with pytest.raises(llm_service.LLMError, match="GEMINI_API_KEY"):
        llm_service.generate_answer("rules", "q")
    assert len(models.calls) == 1   # every model shares the key, so don't waste calls


def test_gemma_gets_rules_inside_the_message(chain):
    models = chain({"main-flash-lite": 429, "backup-flash-lite": 429, "gemma-4-31b-it": "ok"})
    llm_service.generate_answer("RULES TEXT", "QUESTION TEXT")
    gemma_call = models.calls[-1]
    assert gemma_call["system"] is None
    assert gemma_call["contents"].startswith("RULES TEXT") and "QUESTION TEXT" in gemma_call["contents"]
    assert models.calls[0]["system"] == "RULES TEXT"   # Gemini models use a real system prompt


def test_all_models_fail_without_ollama(chain):
    chain({"main-flash-lite": 429, "backup-flash-lite": 429, "gemma-4-31b-it": 429})
    with pytest.raises(llm_service.LLMError, match="All models failed.*free-tier limit"):
        llm_service.generate_answer("rules", "q")


def test_ollama_is_the_last_resort(chain, monkeypatch):
    chain({"main-flash-lite": 429, "backup-flash-lite": 429, "gemma-4-31b-it": 503})
    monkeypatch.setattr(llm_service, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(llm_service, "OLLAMA_MODEL", "llama3.2:3b")

    class FakeOllamaResponse:
        status_code = 200

        def json(self):
            return {"message": {"content": "local answer"}}

    sent = {}

    def fake_post(url, json, timeout):
        sent.update(url=url, body=json)
        return FakeOllamaResponse()

    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    assert llm_service.generate_answer("rules", "q") == ("local answer", "ollama:llama3.2:3b")
    assert sent["url"].endswith("/api/chat")
    assert sent["body"]["messages"][0] == {"role": "system", "content": "rules"}


# ---------- cache ----------
def test_normalize_treats_small_differences_as_same_question():
    assert cache_service.normalize("  What are Apple's RISKS?? ") == "what are apple's risks"


def test_second_identical_question_uses_cache(monkeypatch):
    hit = {"id": "a", "score": 0.6, "text": "header\nApple supply chain risk.",
           "metadata": {"company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026,
                        "report_date": "2026-09-26", "section": "Item 1A. Risk Factors",
                        "document_url": "https://www.sec.gov/a.htm"}}
    calls = []
    monkeypatch.setattr(rag_service, "search", lambda *a, **k: [hit])
    monkeypatch.setattr(rag_service, "generate_answer",
                        lambda s, u: calls.append(1) or ("Supply chain risk [1].", "main-flash-lite"))

    first = rag_service.answer_question("What are Apple's risks?")
    second = rag_service.answer_question("what are apple's risks")
    assert len(calls) == 1                       # second answer came from the cache
    assert first["cached"] is False and second["cached"] is True
    assert second["answer"] == first["answer"]

    rag_service.answer_question("What are Apple's risks?", use_cache=False)
    assert len(calls) == 2                       # --no-cache forces a fresh answer


# ---------- cited-only sources (the "Tesla" fix) ----------
def test_uncited_sources_are_not_shown():
    hits = [{"id": str(n), "score": 0.5, "text": f"h\ntext {n}",
             "metadata": {"company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026,
                          "report_date": "2026-09-26", "section": "Item 7",
                          "document_url": "https://www.sec.gov/a.htm"}} for n in range(3)]
    assert rag_service.format_sources(hits, "FinSight doesn't cover Tesla.") == []
    assert [s["number"] for s in rag_service.format_sources(hits, "Fact [2].")] == [2]
