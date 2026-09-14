"""
Step 03 — Simulation Batch

Runs a batch of synthetic orchestrator queries — covering single-domain
routing, ambiguous multi-domain routing, and the SKU-004 retry case — at
volume, standing in for live production traffic. This is what Step 02's
online evaluation rule scores as it arrives, and what Step 04's dashboard
visualizes as a trend.

Because these queries are synthetic, the correct routing domain(s) for each
is known in advance — used here for a local heuristic sanity check
(routing_accuracy) independent of Step 02's LLM-judge rule, which instead
scores the ORCHESTRATOR'S FINAL ANSWER quality directly against the live
trace, not its internal routing decision. Since routing is now a real LLM
call (agents.py's triage_agent), not a deterministic keyword match, some
routing variance run-to-run is expected and realistic — that variance is
exactly what Step 02's rule and this accuracy check exist to catch.

Usage:
    python 03_simulation/03_simulation.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import flush, run_forecast_query

# (query, sku, expected_domains) — expected_domains is this script's own
# ground truth; the orchestrator never sees it.
QUERY_BANK = [
    ("What's the demand forecast for SKU-001 next period?", "SKU-001", ["forecast"]),
    ("How much SKU-001 do we have on hand?", "SKU-001", ["inventory"]),
    ("Any unusual demand activity across SKU-001?", "SKU-001", ["anomaly"]),
    ("How much SKU-002 do we have in the warehouse?", "SKU-002", ["inventory"]),
    ("What's the forecast trend for SKU-002?", "SKU-002", ["forecast"]),
    ("Forecast and stock check for SKU-002 — are we going to run low?", "SKU-002", ["forecast", "inventory"]),
    ("Why did SKU-003 spike, and will we have enough stock to cover it?", "SKU-003", ["anomaly", "inventory"]),
    ("Is SKU-003's demand forecast expected to keep rising?", "SKU-003", ["forecast"]),
    ("What's the forecast for SKU-004?", "SKU-004", ["forecast"]),  # flaky SKU -> retry, see its trace
    ("Do we have enough SKU-004 in stock for the forecasted demand?", "SKU-004", ["inventory", "forecast"]),
    ("Why did demand drop for SKU-005?", "SKU-005", ["anomaly"]),
    ("What's the reorder status and forecast for SKU-005?", "SKU-005", ["inventory", "forecast"]),
]


async def main():
    correct = 0

    for query, sku, expected_domains in QUERY_BANK:
        result = await run_forecast_query(query, sku)
        routed = set(result["domains_routed"])
        is_correct = routed == set(expected_domains)
        correct += is_correct
        flag = "OK" if is_correct else "MISROUTED"
        print(f"[{flag}] {query!r}  routed={sorted(routed)}  expected={sorted(expected_domains)}")

    flush()
    print(f"\nrouting_accuracy: {correct}/{len(QUERY_BANK)} ({correct / len(QUERY_BANK):.0%})")
    print("Retries: check the SKU-004 traces in the UI for a recovered execute_tool retry.")
    print("\nSee 03_simulation.md for the UI checklist. Proceed to 04_failure_detection/.")


if __name__ == "__main__":
    asyncio.run(main())
