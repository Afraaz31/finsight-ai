"""Public demo mode (the live Hugging Face Space): no uploading or deleting files, no visitors' questions
on the Monitoring page. Everything else works as usual. No AI, no internet."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend import observability as obs
from backend.main import app
from backend.routes import uploads as uploads_route
from frontend import api_client
from tests.test_frontend import SUMMARY, TRACES, open_page
from tests.test_frontend import fake_api  # noqa: F401  (autouse: the UI talks to a fake API)

client = TestClient(app, raise_server_exceptions=False)
SAMPLE = {"doc_id": "abc123def456", "filename": "kestrel_financials.csv", "extension": ".csv", "kind": "table",
          "uploaded_at": "x", "size_bytes": 172,
          "tables": [{"sheet": "csv", "file": "table_0.csv", "rows": 4, "columns": ["Year"],
                      "reshaped_to_long": False}]}


@pytest.fixture
def public_demo(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DEMO", True)
    monkeypatch.setattr(api_client, "PUBLIC_DEMO", True)


def write_trace(question: str) -> None:
    obs.TRACES_FILE.parent.mkdir(parents=True, exist_ok=True)
    obs.TRACES_FILE.write_text(json.dumps({**TRACES[0], "request_id": "r1", "question": question}) + "\n",
                               encoding="utf-8")


# ---------- API ----------
def test_uploading_and_deleting_are_refused(public_demo, monkeypatch):
    monkeypatch.setattr(uploads_route, "add_upload", lambda *a: pytest.fail("must not store the file"))
    monkeypatch.setattr(uploads_route, "delete_upload", lambda *a: pytest.fail("must not delete the file"))
    response = client.post("/uploads", files={"file": ("x.csv", b"Year,Revenue\n2025,1\n", "text/csv")})
    assert response.status_code == 403 and "public demo" in response.json()["detail"]
    assert client.delete("/uploads/abc123def456").status_code == 403


def test_listing_the_sample_files_still_works(public_demo, monkeypatch):
    monkeypatch.setattr(uploads_route, "list_uploads", lambda: [SAMPLE])
    response = client.get("/uploads")
    assert response.status_code == 200 and response.json()[0]["filename"] == "kestrel_financials.csv"


def test_traces_hide_questions_in_public_demo(public_demo):
    write_trace("my private question")
    for url in ("/observability/traces", "/observability/traces?request_id=r1"):
        items = client.get(url).json()
        assert items and all("question" not in t for t in items)
        assert "my private question" not in json.dumps(items)


def test_traces_keep_questions_locally():
    write_trace("What are NVIDIA's risks?")
    assert client.get("/observability/traces").json()[0]["question"] == "What are NVIDIA's risks?"


# ---------- UI ----------
def test_upload_page_has_no_uploader_or_delete_buttons(public_demo, monkeypatch):
    monkeypatch.setattr(api_client, "list_uploads", lambda: [SAMPLE])
    app = open_page("views/upload.py")
    assert not app.exception
    assert any("Public demo" in i.value for i in app.info)
    labels = [b.label for b in app.button]
    assert "✕" not in labels and "📄 Annual report (PDF)" not in labels
    assert len(app.get("file_uploader")) == 0
    assert len(app.checkbox) == 1                       # the sample file can still be ticked


def test_monitoring_hides_the_question_column(public_demo, monkeypatch):
    monkeypatch.setattr(api_client, "observability_summary", lambda: SUMMARY)
    monkeypatch.setattr(api_client, "observability_traces",
                        lambda limit: [{k: v for k, v in TRACES[0].items() if k != "question"}])
    app = open_page("views/monitoring.py")
    assert not app.exception
    assert all("question" not in df.value.columns for df in app.dataframe)
    assert any("abc123" in str(df.value) for df in app.dataframe)


def test_sidebar_says_public_demo(public_demo):
    app = open_page()
    assert any("Public demo" in c.value for c in app.sidebar.caption)
