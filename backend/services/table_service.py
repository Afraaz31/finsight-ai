"""Level 4: questions about uploaded tables (CSV / Excel), answered with EXACT Pandas maths.

Safety design: the LLM never writes or runs code. It only fills in a small JSON "plan"
(which operation, which column, which filters). Python checks the plan and does the maths.

    question + table description ──LLM──► plan (JSON)
    plan ──validate──► execute with Pandas ──► exact numbers
    numbers ──LLM──► plain-English explanation (it may not change the numbers)
"""
import json
import logging
import re

import pandas as pd

from backend.services import number_guard
from backend.services.llm_service import generate_answer

log = logging.getLogger(__name__)

OPERATIONS = {"sum", "mean", "min", "max", "count", "lookup", "top", "growth", "ratio", "describe"}
FILTER_OPS = {"==", "!=", ">", "<", ">=", "<=", "contains"}
YEAR_HEADER = re.compile(r"^(?:FY\s?)?((?:19|20)\d{2})$", re.IGNORECASE)
MAX_RESULT_ROWS = 50


class PlanError(Exception):
    """The plan can't be executed (unknown column, bad operation...). Message is user-safe."""


# =====================================================================
# 1. Preparing a table at upload time
# =====================================================================
def clean_number(value):
    """'$1,234' -> 1234.0   '(500)' -> -500.0   '12.5%' -> 12.5   '—' -> NaN   'abc' -> None"""
    if pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in {"", "-", "—", "–", "n/a", "N/A", "NA"}:
        return float("nan")
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[\s,$€£₹%()]", "", text)
    if text.startswith("-"):
        negative, text = True, text[1:]
    try:
        number = float(text)
    except ValueError:
        return None                     # not a number
    return -number if negative else number


def _numeric_if_mostly_numbers(series: pd.Series, threshold: float = 0.8) -> pd.Series:
    """Convert a text column to numbers if at least 80% of its non-empty cells are numbers."""
    if pd.api.types.is_numeric_dtype(series):
        return series
    non_empty = series.dropna()
    if non_empty.empty:
        return series
    converted = non_empty.map(clean_number)
    ok = converted.map(lambda v: v is not None)
    if ok.mean() < threshold:
        return series
    numbers = series.map(lambda v: clean_number(v) if clean_number(v) is not None else float("nan")).astype(float)
    if numbers.notna().all() and (numbers % 1 == 0).all():
        return numbers.astype("int64")     # whole numbers like years stay 2025, not 2025.0
    return numbers


def _fix_header(df: pd.DataFrame) -> pd.DataFrame:
    """Excel sheets often have title rows above the real header. Find the real header row."""
    unnamed = sum(str(c).startswith("Unnamed") for c in df.columns)
    if unnamed <= len(df.columns) / 2:
        return df
    for i in range(min(10, len(df))):
        row = df.iloc[i]
        if row.notna().mean() >= 0.5:
            new = df.iloc[i + 1:].copy()
            new.columns = [str(v).strip() if pd.notna(v) else f"column_{j}" for j, v in enumerate(row)]
            return new.reset_index(drop=True)
    return df


def to_long_format(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Financial statements are often WIDE: one row per item, one column per year.

        Line Item | 2024 | 2025          Line Item | Period | Value
        Revenue   | 900  | 1000   --->   Revenue   | 2024   | 900
                                          Revenue   | 2025   | 1000
    LONG ("tidy") format lets the same few operations work on every table.
    """
    year_cols = [c for c in df.columns if YEAR_HEADER.match(str(c).strip())]
    if len(year_cols) < 2:
        return df, False
    id_cols = [c for c in df.columns if c not in year_cols]
    long = df.melt(id_vars=id_cols, value_vars=year_cols, var_name="Period", value_name="Value")
    long["Period"] = long["Period"].map(lambda c: int(YEAR_HEADER.match(str(c).strip()).group(1)))
    long["Value"] = long["Value"].map(clean_number).astype(float)
    return long, True


def prepare_table(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Clean one raw table: real header, no empty rows/columns, numbers as numbers, long format."""
    df = _fix_header(df)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    df, reshaped = to_long_format(df)
    for col in df.columns:
        df[col] = _numeric_if_mostly_numbers(df[col])
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].map(lambda v: str(v).strip() if pd.notna(v) else v)
    return df.reset_index(drop=True), reshaped


def describe_columns(df: pd.DataFrame, max_values: int = 20) -> str:
    """Short description of a table for the LLM: columns, types, example values."""
    lines = [f"Rows: {len(df)}"]
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            lines.append(f"- {col!r} (number) e.g. {df[col].dropna().head(3).tolist()}")
        else:
            values = df[col].dropna().unique().tolist()
            shown = values[:max_values]
            more = f" ... (+{len(values) - max_values} more)" if len(values) > max_values else ""
            lines.append(f"- {col!r} (text) values: {shown}{more}")
    return "\n".join(lines)


# =====================================================================
# 2. Plan: what to calculate (filled in by the LLM, checked by Python)
# =====================================================================
PLAN_PROMPT = """You convert a question about a table into a JSON calculation plan. You do NOT \
calculate anything yourself. Reply with ONLY one JSON object, no explanation.

Allowed "operation" values:
- "sum" | "mean" | "min" | "max" | "count": aggregate "column" (count may omit column)
- "lookup": return matching rows (optional "columns": [...] to show)
- "top": rows with the largest "column" values (optional "n", default 5; "ascending": true for smallest)
- "growth": change of "column" over "order_by" (e.g. a year/period column), period by period
- "ratio": numerator / denominator x 100, e.g. a profit margin. Use
  "numerator": {"column": ..., "filters": [...]}, "denominator": {"column": ..., "filters": [...]}
- "describe": general overview / summary of the table

Optional for every operation:
- "filters": [{"column": ..., "op": "==|!=|>|<|>=|<=|contains", "value": ...}]
- "group_by": a column name, to get one result per group (e.g. per year)

Use column names EXACTLY as listed. Use text values exactly as listed for filters.
If the question cannot be answered from these columns, reply {"operation": "unanswerable", \
"reason": "..."}.

Example for a long table with columns Line Item / Period / Value, question "net profit margin by year":
{"operation": "ratio", "numerator": {"column": "Value", "filters": [{"column": "Line Item", "op": "==", \
"value": "Net Income"}]}, "denominator": {"column": "Value", "filters": [{"column": "Line Item", \
"op": "==", "value": "Revenue"}]}, "group_by": "Period"}"""


def parse_plan(text: str) -> dict:
    """Get the JSON object out of the LLM reply (it sometimes wraps it in ```json fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise PlanError("The model did not return a calculation plan. Try naming the column.")
    try:
        plan = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PlanError(f"The calculation plan was not valid JSON ({exc}).") from exc
    if not isinstance(plan, dict):
        raise PlanError("The calculation plan was not a JSON object.")
    return plan


def _resolve(df: pd.DataFrame, name) -> str:
    """Match a column name case-insensitively; unknown -> clear error listing the real columns."""
    if name is None:
        raise PlanError("The plan is missing a column name.")
    for col in df.columns:
        if str(col).strip().lower() == str(name).strip().lower():
            return col
    raise PlanError(f"Column {name!r} not found. Available columns: {list(df.columns)}")


def _apply_filters(df: pd.DataFrame, filters) -> pd.DataFrame:
    for f in filters or []:
        col = _resolve(df, f.get("column"))
        op, value = f.get("op", "=="), f.get("value")
        if op not in FILTER_OPS:
            raise PlanError(f"Unsupported filter operator {op!r}.")
        series = df[col]
        if pd.api.types.is_numeric_dtype(series) and op != "contains":
            target = clean_number(value)
            if target is None:
                raise PlanError(f"Filter value {value!r} is not a number for column {col!r}.")
            mask = {"==": series == target, "!=": series != target, ">": series > target,
                    "<": series < target, ">=": series >= target, "<=": series <= target}[op]
        else:
            text = series.astype(str).str.strip().str.lower()
            target = str(value).strip().lower()
            if op == "contains":
                mask = text.str.contains(target, regex=False)
            elif op in ("==", "!="):
                mask = (text == target) if op == "==" else (text != target)
            else:
                raise PlanError(f"Operator {op!r} needs a number column, but {col!r} is text.")
        df = df[mask]
    return df


def _numeric(df: pd.DataFrame, name) -> str:
    col = _resolve(df, name)
    if not pd.api.types.is_numeric_dtype(df[col]):
        raise PlanError(f"Column {col!r} is text, so it can't be used in a calculation.")
    return col


# =====================================================================
# 3. Execute the plan with Pandas (the only place numbers are produced)
# =====================================================================
def execute_plan(df: pd.DataFrame, plan: dict) -> dict:
    """Run a validated plan. Returns {"summary": str, "table": DataFrame | None}."""
    op = plan.get("operation")
    if op == "unanswerable":
        raise PlanError(plan.get("reason") or "This question can't be answered from the table.")
    if op not in OPERATIONS:
        raise PlanError(f"Unsupported operation {op!r}.")

    data = _apply_filters(df, plan.get("filters"))
    group = _resolve(df, plan["group_by"]) if plan.get("group_by") else None
    if data.empty and op != "describe":
        return {"summary": "No rows match the filters.", "table": None}

    if op in {"sum", "mean", "min", "max"}:
        col = _numeric(df, plan.get("column"))
        if group:
            table = data.groupby(group, sort=True)[col].agg(op).reset_index()
            return {"summary": f"{op} of {col!r} per {group!r} ({len(data)} rows used)", "table": table}
        value = getattr(data[col], op)()
        return {"summary": f"{op} of {col!r} = {value:,.2f} ({len(data)} rows used)", "table": None}

    if op == "count":
        if group:
            table = data.groupby(group).size().reset_index(name="count")
            return {"summary": f"row count per {group!r}", "table": table}
        return {"summary": f"count = {len(data)} rows", "table": None}

    if op == "lookup":
        cols = [_resolve(df, c) for c in plan.get("columns") or []] or list(data.columns)
        return {"summary": f"{len(data)} matching rows", "table": data[cols].head(MAX_RESULT_ROWS)}

    if op == "top":
        col = _numeric(df, plan.get("column"))
        n = max(1, min(int(plan.get("n", 5)), MAX_RESULT_ROWS))
        ascending = bool(plan.get("ascending", False))
        table = data.sort_values(col, ascending=ascending).head(n)
        return {"summary": f"{'lowest' if ascending else 'highest'} {n} rows by {col!r}", "table": table}

    if op == "growth":
        col = _numeric(df, plan.get("column"))
        order = _resolve(df, plan.get("order_by") or plan.get("group_by"))
        series = data.groupby(order, sort=True)[col].sum()
        table = pd.DataFrame({order: series.index, col: series.values})
        table["change"] = table[col].diff()
        table["change_%"] = (table[col].pct_change() * 100).round(2)
        first, last = series.iloc[0], series.iloc[-1]
        overall = (f"{col!r} went from {first:,.2f} ({series.index[0]}) to {last:,.2f} "
                   f"({series.index[-1]}): change {last - first:+,.2f}")
        if first:
            overall += f" ({(last - first) / abs(first) * 100:+.2f}%)"
        return {"summary": overall, "table": table}

    if op == "ratio":
        num, den = plan.get("numerator") or {}, plan.get("denominator") or {}
        num_col, den_col = _numeric(df, num.get("column")), _numeric(df, den.get("column"))
        num_data, den_data = _apply_filters(data, num.get("filters")), _apply_filters(data, den.get("filters"))
        if group:
            n_sum, d_sum = num_data.groupby(group)[num_col].sum(), den_data.groupby(group)[den_col].sum()
            table = pd.DataFrame({"numerator": n_sum, "denominator": d_sum}).dropna()
            table["ratio_%"] = (table["numerator"] / table["denominator"] * 100).round(2)
            return {"summary": "ratio = numerator / denominator x 100, per group",
                    "table": table.reset_index()}
        n_total, d_total = num_data[num_col].sum(), den_data[den_col].sum()
        if d_total == 0:
            raise PlanError("The denominator is zero, so the ratio can't be calculated.")
        return {"summary": f"ratio = {n_total:,.2f} / {d_total:,.2f} x 100 = {n_total / d_total * 100:.2f}%",
                "table": None}

    # describe
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
                    and str(c).strip().lower() not in {"year", "period", "fy", "fiscal year"}]  # summing years is meaningless
    table = df[numeric_cols].agg(["count", "sum", "mean", "min", "max"]).T.round(2) if numeric_cols else None
    return {"summary": f"{len(df)} rows, columns: {list(df.columns)}",
            "table": table.reset_index(names="column") if table is not None else None}


# =====================================================================
# 4. The whole table pipeline
# =====================================================================
EXPLAIN_PROMPT = """You are FinSight AI. Explain a calculation result about a user's uploaded table \
in plain English for a non-expert.

Rules:
1. The numbers in RESULT were calculated exactly by Python. Use them as they are. Never recalculate, \
round differently or invent numbers.
2. Name the file (and sheet) the numbers come from.
3. The table does not say its currency or units unless they appear in the column names or values. \
If they don't, say "in the file's units".
4. If the result says no rows matched, say the data was not found in the file. Don't guess.
5. No investment advice. Keep it under about 150 words."""


def table_to_text(table: pd.DataFrame | None) -> str:
    if table is None or table.empty:
        return "(no table)"
    return table.to_string(index=False, float_format=lambda v: f"{v:,.2f}")


def answer_table_question(question: str, df: pd.DataFrame, filename: str, sheet: str) -> dict:
    """Question about one table -> plan (LLM) -> exact maths (Pandas) -> explanation (LLM)."""
    plan_reply, _ = generate_answer(
        PLAN_PROMPT, f"TABLE: {filename} / sheet {sheet}\n{describe_columns(df)}\n\nQUESTION: {question}")
    plan = parse_plan(plan_reply)
    log.info("Plan for %r: %s", question, plan)
    result = execute_plan(df, plan)

    result_text = f"{result['summary']}\n{table_to_text(result['table'])}"
    explanation, model = generate_answer(
        EXPLAIN_PROMPT,
        f"FILE: {filename} (sheet: {sheet})\nQUESTION: {question}\nRESULT:\n{result_text}")
    missing = number_guard.unverified_numbers(explanation, result_text + "\n" + question)
    explanation = number_guard.add_warning(explanation, missing)
    return {
        "answer": explanation,
        "unverified_numbers": missing,
        "calculation": {"plan": plan, "summary": result["summary"],
                        "table": None if result["table"] is None
                        else result["table"].to_dict(orient="records")},
        "sources": [{"filename": filename, "sheet": sheet, "detail": result["summary"]}],
        "model": model,
    }
