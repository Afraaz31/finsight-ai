"""Level 7: decide HOW to answer a question (simple rules, no AI needed).

    narrative -> RAG over the 10-K text            "What are NVIDIA's major risks?"
    numbers   -> exact figures from SEC XBRL data   "Compare Apple's revenue with Microsoft's"
    both      -> figures + explanation from text    "Explain Amazon's operating income"
"""
import re

# Checked in this order: specific phrases before general words ("gross profit" before "profit").
METRIC_WORDS = [
    ("operating_cash_flow", ["operating cash flow", "cash from operations", "cash flow from operations",
                             "cash provided by operating"]),
    ("gross_profit", ["gross profit"]),
    ("operating_income", ["operating income", "operating profit", "income from operations"]),
    ("net_income", ["net income", "net profit", "net earnings", "profit", "earnings"]),
    ("revenue", ["revenue", "net sales", "sales", "turnover", "top line"]),
    ("total_liabilities", ["liabilities"]),
    ("total_assets", ["assets"]),
    ("cash", ["cash and cash equivalents", "cash position", "cash"]),
]
PERFORMANCE_WORDS = ["financial performance", "financials", "financial results", "key figures"]
DEFAULT_PERFORMANCE_METRICS = ["revenue", "operating_income", "net_income"]
# Words that ask for explanation or context -> the 10-K text is needed too.
EXPLAIN_WORDS = ["explain", "why", "driver", "drove", "reason", "what caused", "discuss", "how did",
                 "risk", "strategy", "segment", "competition", "summar", "describe", "outlook"]
MAX_METRICS = 3


def detect_metrics(question: str) -> list[str]:
    q = question.lower()
    found = []
    for metric, words in METRIC_WORDS:
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", q):
                q = re.sub(rf"\b{re.escape(word)}\b", " ", q)   # "net income" must not also count as "income"
                if metric not in found:
                    found.append(metric)
    if "operating_cash_flow" in found and "cash" in found:
        found.remove("cash")
    if not found and any(w in question.lower() for w in PERFORMANCE_WORDS):
        found = list(DEFAULT_PERFORMANCE_METRICS)
    return found[:MAX_METRICS]


def route(question: str) -> dict:
    """{"route": "narrative" | "numbers" | "both", "metrics": [...]}"""
    metrics = detect_metrics(question)
    if not metrics:
        return {"route": "narrative", "metrics": []}
    q = question.lower()
    explain = any(w in q for w in EXPLAIN_WORDS)
    return {"route": "both" if explain else "numbers", "metrics": metrics}
