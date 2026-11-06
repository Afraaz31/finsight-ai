"""Shared test setup: every test gets its own empty answer cache, so tests never read or
write your real cache in data/cache/ and never affect each other."""
import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    from backend.services import cache_service
    monkeypatch.setattr(cache_service, "CACHE_DIR", tmp_path / "answers")
