"""Number guard: every important number in an LLM answer must appear in the evidence.

The prompt already says "never calculate", but an LLM can still slip. This check catches it:
numbers that are not found in the evidence get a visible warning instead of passing silently.
"""
import re

NUMBER = re.compile(r"\$?\(?-?\d[\d,]*(?:\.\d+)?\)?%?")
CITATION = re.compile(r"\[\d+\]")
SCALES = (1, 1000, 0.001)   # "$478.8 billion" vs "478,834 (millions)"


def _parse(token: str) -> tuple[float, int, bool] | None:
    """'$1,234.5' -> (1234.5, 1 decimal, is_money_or_percent=True)."""
    special = "$" in token or "%" in token
    raw = token.strip("$()%").replace(",", "")
    if not raw or raw in {"-", "."}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return value, decimals, special


def _important(value: float, decimals: int, special: bool) -> bool:
    """Skip small counts ("3 risks"), years and page numbers; check money, %, decimals, big numbers."""
    if decimals == 0 and 1900 <= value <= 2100 and not special:
        return False
    return special or decimals > 0 or abs(value) >= 100


def numbers_in(text: str) -> list[tuple[str, float, int, bool]]:
    found = []
    for token in NUMBER.findall(CITATION.sub(" ", text)):
        parsed = _parse(token)
        if parsed and _important(*parsed):
            found.append((token, *parsed))
    return found


def unverified_numbers(answer: str, evidence: str) -> list[str]:
    """Numbers in the answer that can't be found in the evidence (allowing rounding and k/M/B scale)."""
    known = [p[0] for t in NUMBER.findall(evidence) if (p := _parse(t))]
    missing = []
    for token, value, decimals, _ in numbers_in(answer):
        ok = any(round(abs(k) * s, decimals) == round(abs(value), decimals) for k in known for s in SCALES)
        if not ok:
            missing.append(token)
    return missing


def add_warning(answer: str, missing: list[str]) -> str:
    if not missing:
        return answer
    shown = ", ".join(dict.fromkeys(missing))
    return (answer + f"\n\n⚠ Check: the figure(s) {shown} do not appear in the sources. "
            "They may be the model's own calculation - verify them before relying on them.")


CITATION = re.compile(r" ?\[(\d{1,3})\]")


def drop_unknown_citations(answer: str, source_count: int) -> str:
    """Remove [n] citations that point to no source. Real case: an answer built from 5 passages cited [10];
    a citation that leads nowhere looks like evidence but isn't. [F] (the exact figures) is left alone."""
    return CITATION.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= source_count else "", answer)
