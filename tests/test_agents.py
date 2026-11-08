"""Level 12: Orchestrator + Spreadsheet Agent + Document Agent.

Real sample files (fictional Kestrel data), real Pandas maths; the LLM and the search are fakes,
so no quota and no internet are used.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agents import document_agent, orchestrator, spreadsheet_agent
from backend.main import app
from backend.services import upload_service
from backend.services.llm_service import LLMError
from backend.services.upload_service import UploadError

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
pytestmark = pytest.mark.skipif(not SAMPLES.exists(), reason="samples/ folder missing")
client = TestClient(app)


class FakeLLM:
    """Answers by prompt type, and records every call so tests can check who was asked what."""

    def __init__(self, planner=None, combine="Revenue was 441.2 in the spreadsheet [T1] and $441.2 million in the "
                                             "memo [1]; the two files agree."):
        self.planner, self.combine, self.calls = planner, combine, []

    def __call__(self, system, user):
        self.calls.append((system.split("\n")[0][:40], user))
        if system.startswith("You are the Orchestrator"):
            if isinstance(self.planner, Exception):
                raise self.planner
            return self.planner, "fake"
        if system.startswith("You convert"):                       # the Spreadsheet Agent's plan
            if "Expenses" in user and "sheets" in user:
                return '{"operation": "top", "column": "Value", "n": 2, "sheet": "Expenses"}', "fake"
            return '{"operation": "sum", "column": "Revenue"}', "fake"
        if system.startswith("You are FinSight AI. Explain"):
            return "Total revenue is 1,502.30 in the file's units.", "fake"
        if system.startswith("You are FinSight AI. Two specialist"):
            return self.combine, "fake"
        return "Q4 2025 revenue was $168.3 million [1].", "fake"     # the Document Agent's answer

    def systems(self):
        return [s for s, _ in self.calls]


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(upload_service, "_index_text", lambda doc_id, filename, pages: len(pages))
    monkeypatch.setattr("backend.services.cache_service.get", lambda key: None)
    monkeypatch.setattr("backend.services.cache_service.put", lambda *a: None)
    up = lambda name: upload_service.add_upload(name, (SAMPLES / name).read_bytes())["doc_id"]   # noqa: E731
    ids = {"csv": up("kestrel_financials.csv"), "xlsx": up("kestrel_statements.xlsx"),
           "memo": up("kestrel_board_memo.txt")}
    hit = {"id": "m1", "score": 0.8, "text": "hdr\nFY2025 revenue was $441.2 million, up 10.7%.",
           "metadata": {"filename": "kestrel_board_memo.txt", "page": 1, "chunk_index": 0}}
    monkeypatch.setattr(document_agent, "retrieve_from_uploads", lambda q, metas: [hit])
    return ids


def use(monkeypatch, llm):
    for mod in (orchestrator, spreadsheet_agent, document_agent):
        monkeypatch.setattr(mod, "generate_answer", llm)
    return llm


def plan_json(**steps):
    return json.dumps({**steps, "reason": "test"})


# ---------- one type of file: rules decide, no planner call ----------
def test_only_spreadsheet_goes_to_spreadsheet_agent(files, monkeypatch):
    llm = use(monkeypatch, FakeLLM())
    res = orchestrator.ask("What is total revenue?", [files["csv"]])
    assert res["orchestrator"]["decided_by"] == "rules"
    assert [a["agent"] for a in res["orchestrator"]["agents"]] == ["Spreadsheet Agent"]
    assert not any(s.startswith("You are the Orchestrator") for s in llm.systems())
    assert res["calculation"]["summary"].startswith("sum of 'Revenue' = 1,502.30")   # exact Pandas maths
    assert res["sources"][0]["ref"] == "T1"


def test_only_document_goes_to_document_agent(files, monkeypatch):
    use(monkeypatch, FakeLLM())
    res = orchestrator.ask("What was Q4 revenue?", [files["memo"]])
    assert [a["agent"] for a in res["orchestrator"]["agents"]] == ["Document Agent"]
    assert res["sources"][0]["number"] == 1 and res["calculations"] == []


# ---------- mixed files: the AI planner decides ----------
def test_planner_can_choose_one_agent(files, monkeypatch):
    llm = use(monkeypatch, FakeLLM(plan_json(spreadsheet={"files": [files["csv"]], "task": "Sum Revenue"},
                                             document=None)))
    res = orchestrator.ask("What is total revenue in the CSV?")          # no files ticked -> all uploads
    assert res["orchestrator"]["decided_by"] == "ai"
    assert [a["agent"] for a in res["orchestrator"]["agents"]] == ["Spreadsheet Agent"]
    assert res["orchestrator"]["agents"][0]["task"] == "Sum Revenue"
    assert "kestrel_board_memo.txt" in llm.calls[0][1]                  # the planner saw every file


def test_both_agents_and_combined_answer(files, monkeypatch):
    llm = use(monkeypatch, FakeLLM(plan_json(
        spreadsheet={"files": [files["csv"]], "task": "Revenue for 2025"},
        document={"files": [files["memo"]], "task": "What revenue does the memo report for FY2025?"})))
    res = orchestrator.ask("Does the revenue in the spreadsheet match the memo?")
    assert [a["agent"] for a in res["orchestrator"]["agents"]] == ["Spreadsheet Agent", "Document Agent"]
    combine_input = next(u for s, u in llm.calls if s.startswith("You are FinSight AI. Two"))
    assert "[T1] kestrel_financials.csv" in combine_input and "[1] kestrel_board_memo.txt" in combine_input
    assert not any(s.startswith("You are FinSight AI. Explain") for s in llm.systems())   # no extra calls
    assert {s.get("ref") or s.get("number") for s in res["sources"]} == {"T1", 1}
    assert res["unverified_numbers"] == []


def test_invented_number_in_combined_answer_is_flagged(files, monkeypatch):
    use(monkeypatch, FakeLLM(plan_json(spreadsheet={"files": [files["csv"]], "task": "t"},
                                       document={"files": [files["memo"]], "task": "t"}),
                             combine="Revenue was $999.9 million [1][T1]."))
    res = orchestrator.ask("Compare revenue")
    assert "$999.9" in res["unverified_numbers"][0]
    assert "⚠ Check" in res["answer"]                                   # the user sees the warning too


@pytest.mark.parametrize("planner", ["no json here", plan_json(spreadsheet={"files": ["not-a-real-id"]}),
                                     LLMError("quota")])
def test_bad_or_missing_plan_falls_back_to_rules(files, monkeypatch, planner):
    use(monkeypatch, FakeLLM(planner))
    res = orchestrator.ask("Tell me about revenue")
    assert res["orchestrator"]["decided_by"] == "rules"
    assert {a["agent"] for a in res["orchestrator"]["agents"]} == {"Spreadsheet Agent", "Document Agent"}


def test_planner_cannot_send_a_pdf_to_the_spreadsheet_agent(files, monkeypatch):
    plan = orchestrator.validate_plan({"spreadsheet": {"files": [files["memo"], files["csv"]], "task": "x"}},
                                      "q", [upload_service.get_upload(i) for i in files.values()])
    assert plan["spreadsheet"]["files"] == [files["csv"]] and plan["document"] is None


# ---------- better Excel support ----------
def test_several_spreadsheets_at_once(files, monkeypatch):
    use(monkeypatch, FakeLLM())
    res = orchestrator.ask("What is total revenue?", [files["csv"], files["xlsx"]])
    # each spreadsheet gets its own plan and result, labelled T1, T2 (multi-sheet Excel: the sheet is chosen)
    assert [(c["ref"], c["filename"], c["sheet"]) for c in res["calculations"]] == [
        ("T1", "kestrel_financials.csv", "csv"), ("T2", "kestrel_statements.xlsx", "Expenses")]
    assert res["calculation"] is None and res["orchestrator"]["agents"][0]["status"] == "done"


# ---------- edge cases + API ----------
def test_no_uploads_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOAD_DIR", tmp_path / "none")
    with pytest.raises(UploadError, match="Upload a file first"):
        orchestrator.ask("anything")


def test_assistant_api(files, monkeypatch):
    use(monkeypatch, FakeLLM())
    r = client.post("/assistant/ask", json={"question": "What is total revenue?", "doc_ids": [files["csv"]],
                                            "use_cache": False})
    assert r.status_code == 200 and r.json()["orchestrator"]["agents"][0]["agent"] == "Spreadsheet Agent"
    assert client.post("/assistant/ask", json={"question": "x"}).status_code == 422
    assert client.post("/assistant/ask", json={"question": "What is it?", "doc_ids": ["abc"]}).status_code == 404


def test_citation_lists_are_split_so_every_source_is_linked():
    """Live check 7: the combined answer wrote [T1, T2] and [1, 2], so T1 and passage 2 were missing."""
    from backend.services.number_guard import drop_unknown_citations
    text = "Revenue 352.40 [T1, T2]; the memo agrees [1, 2]. Values [3, 9] and a list [a, b] stay."
    assert drop_unknown_citations(text, 3) == "Revenue 352.40 [T1][T2]; the memo agrees [1][2]. Values [3] and a list [a, b] stay."


def test_combine_prompt_forbids_adding_units_to_spreadsheet_values():
    """Live checks 3 and 5: the merged answer turned the CSV's 310.00 into "$310.00 million"."""
    assert 'never add "$" or "million"' in orchestrator.COMBINE_PROMPT


def test_planner_reply_with_text_after_the_json_is_still_used(files, monkeypatch):
    """Prewarm case: Gemini wrote the plan and then a second block; the plan must still count (not rules)."""
    reply = plan_json(spreadsheet={"files": [files["csv"]], "task": "Sum Revenue"}) + '\n\nNote: {"extra": true}'
    use(monkeypatch, FakeLLM(reply))
    res = orchestrator.ask("What is total revenue in the CSV?")
    assert res["orchestrator"]["decided_by"] == "ai"
    assert [a["agent"] for a in res["orchestrator"]["agents"]] == ["Spreadsheet Agent"]


def test_agent_with_one_skipped_file_is_still_done(files, monkeypatch):
    """Live check 4: the CSV had no expense lines (skipped), the XLSX answered; the step must not look failed."""
    def llm(system, user):
        if system.startswith("You convert"):
            if "kestrel_financials.csv" in user:
                return '{"operation": "unanswerable", "reason": "no expense lines"}', "fake"
            return '{"operation": "top", "column": "Value", "sheet": "Expenses"}', "fake"
        return "The biggest expenses are listed in the table.", "fake"
    use(monkeypatch, llm)
    res = orchestrator.ask("What were the biggest expenses?", [files["csv"], files["xlsx"]])
    status = res["orchestrator"]["agents"][0]["status"]
    assert status.startswith("done · skipped kestrel_financials.csv") and len(res["calculations"]) == 1
