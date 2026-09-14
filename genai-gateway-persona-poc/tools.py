"""
Synthetic, fully offline tool for the AcmeChat docs_rag persona.

Deterministic (same input -> same output) and grounded in a tiny static
corpus loaded by data_store.py. Wrapped in `@opik.track(type="tool")` so it
shows up as its own span nested under the docs_rag handler's span in the
Opik trace tree.

TODO(SE): swap this for the real retriever once known (see rag.py in
modular-agentic-chatbot for a ChromaDB pattern).
"""
import re

import opik

from data_store import KNOWLEDGE_BASE


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _keyword_overlap_score(query: str, text: str) -> float:
    """Fraction of query tokens also present in `text`. Deterministic, no embeddings."""
    q, t = _tokens(query), _tokens(text)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


@opik.track(type="tool")
def search_internal_docs(query: str, top_k: int = 2) -> dict:
    """docs_rag tool: keyword-overlap retrieval over the internal knowledge base."""
    scored = sorted(
        KNOWLEDGE_BASE,
        key=lambda doc: _keyword_overlap_score(query, doc["title"] + " " + doc["content"]),
        reverse=True,
    )
    top = [
        doc for doc in scored[:top_k]
        if _keyword_overlap_score(query, doc["title"] + " " + doc["content"]) > 0
    ]
    if not top:
        # Always ground on *something* so the persona has content to cite —
        # mirrors a retriever with a non-empty fallback (e.g. top-1 by score
        # even below a relevance threshold) rather than an empty-context path.
        top = scored[:1]
    return {"documents": top, "doc_ids": [d["id"] for d in top]}
