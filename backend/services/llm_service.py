"""Talks to Google Gemini. The ONLY file in the project that calls the LLM.

Free tier only: this file never enables billing or switches to a paid model.
"""
import logging
import time

from google import genai
from google.genai import errors, types

from backend.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_TEMPERATURE, require

log = logging.getLogger(__name__)

TIMEOUT_MS = 120_000  # give up on one Gemini call after 120 s instead of waiting forever

_client = None


class LLMError(Exception):
    """A Gemini problem, with a message that is safe to show to the user."""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=require("GEMINI_API_KEY", GEMINI_API_KEY),
                               http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _client


def friendly_message(code: int, detail: str = "") -> str:
    """Turn a Gemini error code into a plain-English explanation."""
    if code == 429:
        return ("Gemini free-tier limit reached. If you sent many questions in the last minute, "
                "wait 60 seconds. If the daily limit is used up, it resets at midnight Pacific time "
                "(about 1:30 PM IST). FinSight never switches to a paid plan automatically.")
    if code == 404:
        return (f"Gemini model '{GEMINI_MODEL}' was not found. Run  python -m scripts.check_gemini  "
                "and put an available 'flash' model name in GEMINI_MODEL in your .env file.")
    if code in (400, 401, 403):
        return f"Gemini rejected the request (code {code}). Check GEMINI_API_KEY in .env. Detail: {detail}"
    if code >= 500:
        return "Gemini is temporarily unavailable or overloaded. Try again in a minute."
    return f"Gemini error {code}: {detail}"


def generate(system_prompt: str, user_prompt: str) -> str:
    """Send one prompt to Gemini and return its text answer. Retries once if Gemini is overloaded."""
    try:
        client = get_client()
    except RuntimeError as exc:  # missing or placeholder API key in .env
        raise LLMError(str(exc)) from exc

    config = types.GenerateContentConfig(system_instruction=system_prompt,
                                         temperature=LLM_TEMPERATURE)
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=user_prompt, config=config)
        except errors.APIError as exc:
            if exc.code >= 500 and attempt == 1:
                log.warning("Gemini returned %s, retrying once in 3 s ...", exc.code)
                time.sleep(3)
                continue
            raise LLMError(friendly_message(exc.code, exc.message or "")) from exc
        except Exception as exc:  # no internet, DNS failure, timeout ...
            raise LLMError(f"Could not reach Gemini: {exc}") from exc

        text = response.text
        if not text:
            raise LLMError("Gemini returned an empty answer (it may have been blocked by a safety "
                           "filter). Try rephrasing the question.")
        return text.strip()
    raise LLMError("Gemini is temporarily unavailable. Try again in a minute.")
