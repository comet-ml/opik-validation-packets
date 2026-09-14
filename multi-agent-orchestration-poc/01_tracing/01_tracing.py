"""
Step 01 — Tracing

Exercises the demand-forecasting orchestrator through a handful of sample
queries chosen to exercise every trace-shape case this PoC demonstrates:
single-domain routing, ambiguous multi-domain routing (real LLM-driven
fan-out to more than one specialist agent), and a retry after a simulated
transient tool failure.

Every agent involved (triage, each specialist, synthesis) is a real
`agent_framework.Agent` — Microsoft Agent Framework has no native Opik
integration, so its own real OpenTelemetry auto-instrumentation is what
produces these spans (see otel_setup.py), bridged into the SAME Opik trace
as the outer `orchestrator_run` @opik.track span via OpikSpanProcessor — one
merged trace per query:

    orchestrator_run                     <- @opik.track boundary (this module)
      invoke_agent triage_agent           <- real agent_framework span tree
        chat gpt-4o-mini
        execute_tool needs_*_agent (1+)
        chat gpt-4o-mini
      invoke_agent <specialist>_agent     <- one per routed domain
        chat gpt-4o-mini
        execute_tool <specialist>_lookup   <- 2x on the SKU-004 retry case
        chat gpt-4o-mini
      invoke_agent synthesis_agent
        chat gpt-4o-mini

Docs: https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/

Usage:
    python 01_tracing/01_tracing.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import flush, run_forecast_query

SAMPLE_QUERIES = [
    ("What's the demand forecast for SKU-001 next period?", "SKU-001"),               # single-domain: forecast
    ("How much SKU-002 do we have on hand right now?", "SKU-002"),                     # single-domain: inventory
    ("Why did demand spike for SKU-003, and will we have enough stock?", "SKU-003"),   # ambiguous: anomaly + inventory
    ("What's the forecast for SKU-004?", "SKU-004"),                                   # triggers one retry (flaky SKU)
]


async def main():
    for query, sku in SAMPLE_QUERIES:
        result = await run_forecast_query(query, sku)
        print(f"[OK] {query!r}  domains={result['domains_routed']}  ambiguous={result['ambiguous']}")

    flush()
    print("Done. See 01_tracing.md for the UI checklist.")


if __name__ == "__main__":
    asyncio.run(main())
