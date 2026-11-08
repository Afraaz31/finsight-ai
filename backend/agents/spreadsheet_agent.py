"""Spreadsheet Agent: answers questions about Excel / CSV files with EXACT maths.

Its job, for each spreadsheet it is given:
    1. show Gemini the columns (never the whole table) and get a JSON calculation plan
    2. Python checks the plan and runs it with Pandas (no AI-written code is ever executed)
    3. report the result, labelled [T1], [T2] ... so the Orchestrator can cite it
Multi-sheet Excel files: Gemini also picks the sheet that fits the task.
"""
import logging

from backend.services import number_guard
from backend.services.llm_service import generate_answer
from backend.services.table_service import (EXPLAIN_PROMPT, PLAN_PROMPT, PlanError, describe_columns,
                                            execute_plan, parse_plan, table_to_text)
from backend.services.upload_service import load_table

log = logging.getLogger(__name__)
NAME = "Spreadsheet Agent"


def _plan_prompt(task: str, meta: dict, sheet: str | None) -> tuple[str, list[str]]:
    """Describe the table(s) for the planner. Several sheets -> describe each and let it choose."""
    sheets = [t["sheet"] for t in meta["tables"]]
    if sheet or len(sheets) == 1:
        df, name = load_table(meta["doc_id"], sheet)
        return f"TABLE: {meta['filename']} / sheet {name}\n{describe_columns(df)}\n\nQUESTION: {task}", [name]
    parts = []
    for name in sheets:
        df, _ = load_table(meta["doc_id"], name)
        parts.append(f"SHEET \"{name}\":\n{describe_columns(df)}")
    return (f"FILE: {meta['filename']} has {len(sheets)} sheets.\n\n" + "\n\n".join(parts)
            + "\n\nAdd \"sheet\": \"<sheet name>\" to the plan to choose the sheet that answers the question."
            + f"\n\nQUESTION: {task}"), sheets


def run(task: str, metas: list[dict], sheet: str | None = None, explain: bool = True,
        first_ref: int = 1) -> dict:
    """Run the task on every spreadsheet given. explain=True: also write a short answer (used when this
    agent works alone; when both agents work, the Orchestrator writes the answer instead)."""
    calculations, errors, evidence = [], [], []
    for i, meta in enumerate(metas, first_ref):
        ref = f"T{i}"
        try:
            prompt, sheets = _plan_prompt(task, meta, sheet)
            plan = parse_plan(generate_answer(PLAN_PROMPT, prompt)[0])
            chosen = plan.pop("sheet", None)
            chosen = chosen if chosen in sheets else sheets[0]
            df, chosen = load_table(meta["doc_id"], chosen)
            result = execute_plan(df, plan)
        except PlanError as exc:
            errors.append(f"{meta['filename']}: {exc}")
            continue
        table = None if result["table"] is None else result["table"].to_dict(orient="records")
        calculations.append({"ref": ref, "filename": meta["filename"], "sheet": chosen, "plan": plan,
                             "summary": result["summary"], "table": table})
        evidence.append(f"[{ref}] {meta['filename']} (sheet {chosen}): {result['summary']}\n"
                        f"{table_to_text(result['table'])}")
        log.info("%s %s on %s/%s: %s", NAME, ref, meta["filename"], chosen, plan)

    answer, model = None, None
    if explain and calculations:
        answer, model = generate_answer(EXPLAIN_PROMPT, f"QUESTION: {task}\nRESULTS (calculated by Python):\n"
                                                        + "\n\n".join(evidence))
        answer = number_guard.drop_unknown_citations(answer, 0)       # its results are [T1]..., never [n]
    elif explain and errors:
        answer = "I couldn't calculate this from the spreadsheet(s): " + "; ".join(errors)
    return {"agent": NAME, "task": task, "files": [m["filename"] for m in metas], "answer": answer,
            "model": model, "calculations": calculations, "errors": errors, "evidence": "\n\n".join(evidence),
            "sources": [{"filename": c["filename"], "sheet": c["sheet"], "detail": c["summary"], "ref": c["ref"]}
                        for c in calculations]}
