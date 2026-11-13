"""Exact-spot links into SEC filings using URL "text fragments".

A link like  https://www.sec.gov/...htm#:~:text=Apple%20designs,smartphones
makes Chrome, Edge (and recent Firefox/Safari) scroll to that sentence and highlight it.
So "Open the source" lands on the exact passage, not the top of a 200-page report.
"""
import re
from urllib.parse import quote

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n")
WORD = re.compile(r"\S+")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
# Bullets and footnote markers are separate elements on the SEC page ("•" then "changes in..."), but the
# cleaned text glues them to the first word ("•changes"), so the browser can't find them: strip them.
LEADING_MARKER = re.compile(r"^(?:[•◦▪●■□➢*–—-]+|\(\s*(?:\d{1,2}|[a-zA-Z])\s*\))\s*")


def _encode(text: str) -> str:
    # In text fragments, "-", "," and "&" have special meanings, so they must be percent-encoded.
    return quote(text, safe="").replace("-", "%2D")


def pick_anchor_sentence(text: str) -> str | None:
    """A plain prose sentence from the passage that the browser can find on the page.

    Skips table rows ("a | b"), sentences whose anchor words hold numbers and ALL-CAPS headings
    ("ITEM 7.MANAGEMENT'S..."), whose formatting on the web page may differ, and strips leading bullets
    and footnote markers.
    """
    for sentence in SENTENCE_SPLIT.split(text or ""):
        s = LEADING_MARKER.sub("", sentence.strip()).strip()
        words = WORD.findall(s)
        if len(words) < 8 or len(s) > 1000 or "|" in s:
            continue
        # Only the start and end words go into the link (the browser highlights everything between),
        # so only THEY must avoid numbers, whose formatting on the page may differ. Dates in the middle
        # ("as of January 25, 2026") are fine - that keeps audit opinions linkable.
        anchor_words = YEAR.sub("", " ".join(words[:5] + words[-4:]))   # years ("since 2004.") look the same
        if any(ch.isdigit() for ch in anchor_words):
            continue
        letters = [ch for ch in s if ch.isalpha()]
        if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.6:   # a heading
            continue
        return s
    return None


def deep_link(url: str, passage: str) -> str:
    """URL that opens the document at the passage (falls back to the plain URL)."""
    sentence = pick_anchor_sentence(passage)
    if not url or not sentence:
        return url
    words = WORD.findall(sentence)
    start, end = " ".join(words[:5]), " ".join(words[-4:])
    return f"{url}#:~:text={_encode(start)},{_encode(end)}"
