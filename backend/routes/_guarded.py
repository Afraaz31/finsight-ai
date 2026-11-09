"""Level 13: the same guardrail steps for every question endpoint (kept out of the routes' logic)."""
from backend import guardrails
from backend import observability as obs


def before(question: str) -> None:
    """Input guardrails + remember the (redacted) question in the trace."""
    obs.set_field("question", guardrails.redact_pii(question)[0][:300])
    guardrails.check_input(question)          # raises GuardrailBlocked -> HTTP 400


def expects_citations(result: dict) -> bool:
    """An answer built from citable sources (10-K passages [n], document passages [n], spreadsheet
    results [T1]) should cite at least one. The report's intro line is written by Python (its AI
    sections are checked separately), and a plain table answer has nothing to cite."""
    if result.get("route") == "report":
        return False
    return any(s.get("number") is not None or s.get("ref") for s in result.get("sources") or [])


def after(result: dict, text_key: str = "answer") -> dict:
    """Output guardrails on the answer, then attach the guardrail results and the request id."""
    if result.get(text_key):
        result = {**result, text_key: guardrails.check_output(result[text_key], expects_citations(result))}
    if result.get("report"):
        result["report"] = guardrails.check_report(result["report"])
    obs.record_guardrail("output_checks", "passed")
    if result.get("route"):
        obs.set_field("route", result["route"])
    obs.set_field("cached", result.get("cached"))
    obs.event("number_guard", flagged=len(result.get("unverified_numbers") or []))
    t = obs.current()
    return {**result, "guardrails": guardrails.summary_for_response(), "request_id": t["request_id"] if t else None}
