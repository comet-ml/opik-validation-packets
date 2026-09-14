"""
Loads the tiny static/synthetic corpus used by tools.py.

Fully offline — no network calls, no vector DB. Retrieval is a deterministic
keyword-overlap match (see tools._keyword_overlap_score), which keeps the
packet reproducible without any embedding model.

TODO(SE): once the real customer's retriever is known, replace this JSON file
(and the matching logic in tools.py) with the real integration. This module
is the single place all of that data is loaded from.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str):
    with open(DATA_DIR / name) as f:
        return json.load(f)


KNOWLEDGE_BASE = _load("knowledge_base.json")  # list[{id, title, category, content}]
