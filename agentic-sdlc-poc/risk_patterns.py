"""
Sensitive-data-in-prompt risk detector — one worked risk-category pattern.

Deterministic, regex-based, no model call: scans a block of text (a chat
span's captured prompt/completion, or a tool span's captured
arguments/result — see copilot_session.py's GOTCHA 2 on `capture_content`)
for shapes that commonly indicate a developer pasted a secret into a Copilot
Chat turn. Used by Step 04 of this packet (not built yet — this module is
just the detector).

Kept simple and explainable on purpose: plain regex, no ML, no external
calls — every match is directly justifiable to a security reviewer by
pointing at the pattern that fired.

Tune/extend these patterns against the customer's real secret formats
(internal API key prefixes, internal ticket/PII formats, etc.) once known.
"""
import re
from typing import List, Dict

PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "generic_api_key_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}['\"]?"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # 13-16 digit run, optionally grouped by spaces/dashes in blocks of 4 — a
    # loose credit-card-shaped match, not a Luhn-validated one (deliberately
    # simple per this packet's scope).
    "credit_card_like": re.compile(r"\b(?:\d[ -]?){12,15}\d\b"),
}


def scan_for_sensitive_data(text: str) -> List[Dict]:
    """Return a list of {category, match, start} dicts for every pattern hit in `text`."""
    if not text:
        return []

    matches = []
    for category, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append({"category": category, "match": m.group(0), "start": m.start()})
    return matches
