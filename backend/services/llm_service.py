"""Talks to the LLM. The ONLY file in the project that calls Gemini (or the local Ollama backup).

Quota Shield: try GEMINI_MODEL first, then each model in GEMINI_FALLBACK_MODELS (each has its own
free daily quota), then optionally a local Ollama model. Free tier only: never enables billing.

Level 13: before any model is called, personal data is redacted (guardrail) and the daily budget is
checked; every call is recorded in the request's trace with its latency and token counts.
"""
import logging
import time

import requests
from google import genai
from google.genai import errors, types

from backend import observability as obs
from backend.config import (DAILY_LLM_CALL_LIMIT, GEMINI_API_KEY, GEMINI_FALLBACK_MODELS, GEMINI_MODEL,
                            LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, OLLAMA_ENABLED, OLLAMA_MODEL,
                            OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL, require)

log = logging.getLogger(__name__)

_client = None

# Errors where trying the NEXT model can help (each model has its own quota / capacity).
TRY_NEXT_MODEL = {404, 429, 500, 502, 503, 504}


class LLMError(Exception):
    """An LLM problem, with a message that is safe to show to the user."""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=require("GEMINI_API_KEY", GEMINI_API_KEY),
            http_options=types.HttpOptions(timeout=LLM_TIMEOUT_SECONDS * 1000),  # milliseconds
        )
    return _client


def model_chain() -> list[str]:
    """Main model first, then fallbacks, without duplicates."""
    chain = []
    for model in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
        if model and model not in chain:
            chain.append(model)
    return chain


def friendly_message(code: int, detail: str = "") -> str:
    """Turn a Gemini error code into a plain-English explanation."""
    if code == 429:
        return ("Gemini free-tier limit reached. If you sent many questions in the last minute, "
                "wait 60 seconds. If the daily limit is used up, it resets at midnight Pacific time "
                "(about 1:30 PM IST). FinSight never switches to a paid plan automatically.")
    if code == 404:
        return ("Gemini model not found. Run  python -m scripts.check_gemini  and fix GEMINI_MODEL / "
                "GEMINI_FALLBACK_MODELS in your .env file.")
    if code in (400, 401, 403):
        return f"Gemini rejected the request (code {code}). Check GEMINI_API_KEY in .env. Detail: {detail}"
    if code >= 500:
        return "Gemini is temporarily unavailable or overloaded. Try again in a minute."
    return f"Gemini error {code}: {detail}"


def _call_gemini(model: str, system_prompt: str, user_prompt: str) -> str:
    """One request to one Gemini-API model."""
    if model.startswith("gemma"):
        # Gemma models on the Gemini API don't accept a separate system instruction,
        # so the rules are placed at the top of the user message instead.
        contents = f"{system_prompt}\n\n{user_prompt}"
        config = types.GenerateContentConfig(temperature=LLM_TEMPERATURE)
    else:
        contents = user_prompt
        config = types.GenerateContentConfig(system_instruction=system_prompt,
                                             temperature=LLM_TEMPERATURE)
    t0 = time.perf_counter()
    try:
        response = get_client().models.generate_content(model=model, contents=contents, config=config)
    except errors.APIError as exc:
        obs.record_llm_call(model, False, (time.perf_counter() - t0) * 1000, error=f"HTTP {exc.code}")
        raise
    except Exception as exc:
        obs.record_llm_call(model, False, (time.perf_counter() - t0) * 1000, error=type(exc).__name__)
        raise
    usage = getattr(response, "usage_metadata", None)            # token counts, for observability
    text = response.text
    obs.record_llm_call(model, bool(text), (time.perf_counter() - t0) * 1000,
                        getattr(usage, "prompt_token_count", None), getattr(usage, "candidates_token_count", None),
                        None if text else "empty answer")
    if not text:
        raise LLMError("empty answer (possibly blocked by a safety filter)")
    return text.strip()


def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Local backup model via Ollama (free, unlimited, offline; slower on CPU)."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "system", "content": system_prompt},
                             {"role": "user", "content": user_prompt}],
                "stream": False,
                "options": {"temperature": LLM_TEMPERATURE},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LLMError(f"Ollama is not reachable at {OLLAMA_URL} (is the Ollama app running?): {exc}")
    if response.status_code != 200:
        raise LLMError(f"Ollama returned {response.status_code}: {response.text[:200]} "
                       f"(did you run  ollama pull {OLLAMA_MODEL} ?)")
    text = response.json().get("message", {}).get("content", "").strip()
    if not text:
        raise LLMError("Ollama returned an empty answer.")
    return text


def _call_ollama_observed(system_prompt: str, user_prompt: str) -> str:
    """_call_ollama, timed and recorded in the trace (no token counts from Ollama)."""
    t0, model = time.perf_counter(), f"ollama:{OLLAMA_MODEL}"
    try:
        text = _call_ollama(system_prompt, user_prompt)
    except LLMError as exc:
        obs.record_llm_call(model, False, (time.perf_counter() - t0) * 1000, error=str(exc)[:120])
        raise
    obs.record_llm_call(model, True, (time.perf_counter() - t0) * 1000)
    return text


def generate_answer(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """Return (answer_text, model_used). Walks the Quota Shield chain until one model answers."""
    from backend.guardrails import redact_pii      # local import: guardrails imports observability too
    system_prompt, _ = redact_pii(system_prompt)
    user_prompt, found = redact_pii(user_prompt)
    if found:
        obs.record_guardrail("pii_redaction", "redacted", ", ".join(f"{k}×{v}" for k, v in found.items()))

    budget_left = obs.llm_calls_today() < DAILY_LLM_CALL_LIMIT
    if not budget_left:
        obs.record_guardrail("daily_ai_budget", "blocked", f"{DAILY_LLM_CALL_LIMIT} Gemini calls reached today")
    try:
        get_client()
    except RuntimeError as exc:  # missing or placeholder API key in .env
        raise LLMError(str(exc)) from exc

    # keep the "<what>: <reason>" format: last_code below splits on ": "
    failures = [] if budget_left else [f"daily budget: {DAILY_LLM_CALL_LIMIT} Gemini calls reached today"]
    for model in (model_chain() if budget_left else []):
        try:
            text = _call_gemini(model, system_prompt, user_prompt)
            if failures:
                log.warning("Answered by fallback model %s after: %s", model, "; ".join(failures))
            return text, model
        except errors.APIError as exc:
            if exc.code not in TRY_NEXT_MODEL:
                # bad key / bad request: every model would fail the same way
                raise LLMError(friendly_message(exc.code, exc.message or "")) from exc
            failures.append(f"{model}: {exc.code}")
            log.warning("Model %s failed with %s, trying the next one", model, exc.code)
        except LLMError as exc:
            failures.append(f"{model}: {exc}")
        except Exception as exc:  # timeout, no internet, DNS ...
            failures.append(f"{model}: {type(exc).__name__}")
            log.warning("Model %s failed (%s), trying the next one", model, exc)

    if OLLAMA_ENABLED:
        log.warning("All Gemini models failed (%s). Using local Ollama model %s.",
                    "; ".join(failures), OLLAMA_MODEL)
        return _call_ollama_observed(system_prompt, user_prompt), f"ollama:{OLLAMA_MODEL}"

    last_code = next((int(f.rsplit(": ", 1)[1]) for f in reversed(failures)
                      if f.rsplit(": ", 1)[1].isdigit()), 0)
    hint = friendly_message(last_code) if last_code else "Check your internet connection."
    if not budget_left:
        raise LLMError(f"FinSight's daily budget of {DAILY_LLM_CALL_LIMIT} Gemini calls is used up, so Gemini "
                       "was not called. It resets at midnight UTC. Saved answers and exact SEC figures still work.")
    raise LLMError(f"All models failed ({'; '.join(failures)}). {hint}")


def generate(system_prompt: str, user_prompt: str) -> str:
    """Convenience wrapper: just the answer text."""
    return generate_answer(system_prompt, user_prompt)[0]
