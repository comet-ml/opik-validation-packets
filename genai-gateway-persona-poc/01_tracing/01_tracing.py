"""
Step 01 — Tracing

Exercises the AcmeChat docs_rag persona through the real custom-code app
(gateway -> docs_rag handler -> tool -> LLM) — plain Python function calls,
no agent framework — instrumented with `@opik.track` on the gateway/handler
functions and Opik's native `track_openai`/`track_anthropic` client wrappers
for the LLM call itself. Every call produces ONE Opik trace with two visible
layers:

    gateway_ingress                 (span — routing target)
      docs_rag                      (span — tool call + LLM generation)
        search_internal_docs        (span — called on every query)
        chat_completion_create |
        anthropic_messages_create   (span — token usage + cost)

A few distinct queries are run directly (no persona-keyed dict needed —
there's only one persona) to show the trace shape stays identical while the
retrieved doc(s) and answer vary with the question.

Docs: https://www.comet.com/docs/opik/v1/tracing/integrations/openai/
      https://www.comet.com/docs/opik/v1/tracing/integrations/anthropic/

Usage:
    python 01_tracing/01_tracing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway import flush, handle_request

SAMPLE_QUERIES = [
    "What's Acme's remote work policy?",
    "How many PTO days do full-time employees accrue per year?",
    "How do I reset my AcmeChat password?",
]


def main():
    for query in SAMPLE_QUERIES:
        result = handle_request(query)
        print(f"[OK] {query!r}  tool={result['tool_used']}  doc_ids={result['retrieved_doc_ids']}  trace={result['trace_id']}")

    flush()
    print("Done. See 01_tracing.md for the UI checklist.")


if __name__ == "__main__":
    main()
