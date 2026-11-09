"""Shared test setup: every test gets its own empty answer cache and trace file, so tests never read or
write your real cache in data/cache/ and never affect each other."""
import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    from backend.services import cache_service
    monkeypatch.setattr(cache_service, "CACHE_DIR", tmp_path / "answers")


@pytest.fixture(autouse=True)
def isolated_observability(tmp_path, monkeypatch):
    """Level 13: traces go to a temporary file, and the rate limiter starts empty for every test."""
    from backend import guardrails, observability
    monkeypatch.setattr(observability, "OBS_DIR", tmp_path / "obs")
    monkeypatch.setattr(observability, "TRACES_FILE", tmp_path / "obs" / "traces.jsonl")
    guardrails._hits.clear()
