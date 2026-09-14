"""
Step 04 — Failure Detection

Deliberately injects two DISTINCT known failures and, for each, queries the
Opik API afterward to programmatically confirm the failure is captured and
visible in the trace output — not just "go look in the UI," an automated
pass/fail check matching this use case's criterion word for word: "inject a
known failure into a test run; confirm it appears in Opik's trace output."

Two distinct failure shapes, both real (not simulated after the fact):

    1. Transient, self-healing — agents.py's FLAKY_SKUS (SKU-004): the tool
       raises once, the model retries per its instructions, and succeeds.
       The underlying problem stays visible in the trace (two execute_tool
       spans, the first with error_info) even though the end-to-end call
       succeeded — you don't lose visibility just because something
       recovered.

    2. Permanent, non-recoverable — an unknown SKU ("SKU-000"): the tool
       raises the SAME error on every attempt (a stand-in for "bad tool
       response, malformed upstream data" — the upstream record simply
       doesn't exist). The model retries once per its instructions, fails
       again identically, then gives up gracefully — the orchestrator
       returns a normal natural-language "I'm unable to retrieve this"
       response rather than crashing, while BOTH failed attempts remain
       fully visible (error_info populated) in the trace.

Usage:
    python 04_failure_detection/04_failure_detection.py
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import opik

from orchestrator import flush, run_forecast_query

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")

# Same redirect-URL shape the SDK itself auto-prints ("OPIK: Started logging
# traces to...") — derived from OPIK_URL_OVERRIDE (self-hosted/single-tenant)
# if set, not hardcoded to the standard cloud API base.
_API_BASE = os.getenv("OPIK_URL_OVERRIDE") or "https://www.comet.com/opik/api"
_PATH_B64 = base64.b64encode(_API_BASE.encode()).decode()


def trace_url(trace_id: str) -> str:
    return f"{_API_BASE}/v1/session/redirect/projects/?trace_id={trace_id}&path={_PATH_B64}"

CASES = [
    {
        "label": "transient, self-healing (FLAKY_SKUS)",
        "query": "What's the forecast for SKU-004?",
        "sku": "SKU-004",
        "tool_span_name": "execute_tool forecast_lookup",
        "expect_min_failed_spans": 1,  # exactly 1 failed attempt, then a recovered one
    },
    {
        "label": "permanent, non-recoverable (unknown SKU)",
        "query": "What's the forecast for SKU-000?",
        "sku": "SKU-000",
        "tool_span_name": "execute_tool forecast_lookup",
        "expect_min_failed_spans": 2,  # fails, retries per instructions, fails again identically
    },
]


def count_failed_spans(client: opik.Opik, trace_id: str, span_name: str) -> int:
    spans = client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=trace_id)
    return sum(1 for s in spans if s.name == span_name and s.error_info is not None)


async def main():
    client = opik.Opik()
    results = []

    for case in CASES:
        print(f"--- Injecting: {case['label']} ---")
        result = await run_forecast_query(case["query"], case["sku"])
        print(f"  final response: {result['response']!r}")
        flush()  # ensure spans are written before querying them back

        failed_count = count_failed_spans(client, result["trace_id"], case["tool_span_name"])
        ok = failed_count >= case["expect_min_failed_spans"]
        flag = "OK" if ok else "MISSING"
        print(f"  [{flag}] {failed_count} {case['tool_span_name']!r} span(s) with error_info "
              f"(expected >= {case['expect_min_failed_spans']})")
        print(f"  trace: {trace_url(result['trace_id'])}\n")
        results.append(ok)

    if all(results):
        print(f"All {len(CASES)} injected failures confirmed visible in their traces.")
    else:
        print(f"{results.count(False)}/{len(CASES)} injected failures were NOT found in the trace — investigate.")

    print("\nSee 04_failure_detection.md for the UI checklist. Proceed to 05_retry_detection/.")


if __name__ == "__main__":
    asyncio.run(main())
