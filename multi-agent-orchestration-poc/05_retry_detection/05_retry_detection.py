"""
Step 05 — Retry Detection

Runs a batch of representative queries — 3 that exercise a real retry (one
per specialist tool, all on the flaky SKU-004) and 2 "control" queries that
should show zero retries — then programmatically reviews every resulting
trace's spans to identify and COUNT retry events, rather than just eyeballing
the UI. This matches the use case criterion word for word: "run a batch of
representative queries; review traces for retry/loop patterns; confirm
retries appear as distinct, visible events."

A "retry event" here is detected as: an `execute_tool <name>` span with
`error_info` set, immediately followed by a same-named sibling span WITHOUT
`error_info` — i.e. the tool failed once and then visibly succeeded on a
second attempt within the same agent run (see agents.py's FLAKY_SKUS /
04_failure_detection's transient case for how this is produced).

Usage:
    python 05_retry_detection/05_retry_detection.py
"""
import asyncio
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

# (query, sku, expect_retry) — expect_retry is this script's own ground truth,
# not something the orchestrator sees.
QUERY_BANK = [
    ("What's the forecast for SKU-004?", "SKU-004", True),           # forecast_lookup retries
    ("How much SKU-004 do we have in stock?", "SKU-004", True),      # inventory_lookup retries
    ("Any unusual demand activity for SKU-004?", "SKU-004", True),   # anomaly_lookup retries
    ("What's the forecast for SKU-001?", "SKU-001", False),          # control: no retry
    ("How much SKU-002 do we have on hand?", "SKU-002", False),      # control: no retry
]


def find_retry_events(client: opik.Opik, trace_id: str) -> list:
    """Return [(span_name, failed_span_id, recovered_span_id), ...] for this trace."""
    spans = sorted(client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=trace_id), key=lambda s: s.start_time)
    events = []
    by_name = {}
    for s in spans:
        if not s.name.startswith("execute_tool "):
            continue
        by_name.setdefault(s.name, []).append(s)
    for name, group in by_name.items():
        failed = [s for s in group if s.error_info is not None]
        recovered = [s for s in group if s.error_info is None]
        if failed and recovered:
            events.append((name, failed[0].id, recovered[0].id))
    return events


async def main():
    client = opik.Opik()
    total_events = 0
    correct = 0

    for query, sku, expect_retry in QUERY_BANK:
        result = await run_forecast_query(query, sku)
        flush()  # ensure spans are written before querying them back

        events = find_retry_events(client, result["trace_id"])
        got_retry = len(events) > 0
        is_correct = got_retry == expect_retry
        correct += is_correct
        total_events += len(events)

        flag = "OK" if is_correct else "MISMATCH"
        detail = f"{len(events)} retry event(s): {[e[0] for e in events]}" if events else "no retries"
        print(f"[{flag}] {query!r}  expected_retry={expect_retry}  {detail}")

    print(f"\n{correct}/{len(QUERY_BANK)} queries matched expected retry behavior.")
    print(f"Total retry events found across the batch: {total_events} (identifiable and countable, "
          f"each backed by a real error_info + a recovered sibling span).")
    print("\nSee 05_retry_detection.md for the UI checklist. Proceed to 06_dashboard/.")


if __name__ == "__main__":
    asyncio.run(main())
