"""
The AcmeChat docs_rag handler — plain Python, no agent framework (no
LangGraph, no Semantic Kernel, no Microsoft Agent Framework). gateway.py
wraps this with the outer "gateway" span (see gateway.py's module docstring
for the full trace-shape explanation).

TODO(SE): rewrite this file once the real customer's actual docs_rag handler
is known — the prompt/model below is also where real values go.
"""
from typing import Optional

import opik

import tools
from llm_clients import generate as generate_llm

# Plain module-level constant, not a dict — simulate_config_regression.py
# mutates this directly at runtime, and run_docs_rag() re-reads it on every call.
SYSTEM_PROMPT = (  # TODO(SE): real prompt
    "You are AcmeChat, Acme Corp's internal-documentation assistant. Answer ONLY "
    "using the retrieved document context below — cite the document id (e.g. "
    "[kb-001]). If the context doesn't contain the answer, say so rather than "
    "guessing. Never claim to have taken an action — only describe the procedure."
)


@opik.track(name="docs_rag")
def run_docs_rag(query: str, model: Optional[str] = None) -> dict:
    result = tools.search_internal_docs(query)
    doc_ids = result["doc_ids"]
    context_text = "\n".join(f"[{d['id']}] {d['title']}: {d['content']}" for d in result["documents"])

    user_content = query if not context_text else f"{query}\n\nContext:\n{context_text}"
    model = model or "openai/gpt-4o-mini"  # TODO(SE): real model
    answer = generate_llm(model, SYSTEM_PROMPT, user_content)
    return {
        "response": answer,
        "tool_used": "search_internal_docs",
        "context": context_text,
        "retrieved_doc_ids": doc_ids,
    }
