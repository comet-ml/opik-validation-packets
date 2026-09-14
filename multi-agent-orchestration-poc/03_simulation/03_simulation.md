# Step 03 — Simulation Batch: UI Checklist

Run `python 03_simulation/03_simulation.py`, then verify in Opik UI > Projects > `multi-agent-orchestration-poc` > Traces.

- [ ] 12 new `orchestrator_run` traces appear
- [ ] Console output shows `routing_accuracy` at or near 12/12 — routing is now a real LLM call (`triage_agent`), so an occasional `MISROUTED` is expected/realistic run-to-run variance, not a bug to fix (this is exactly what Step 02's rule and this check exist to catch)
- [ ] The two SKU-004 traces (`What's the forecast for SKU-004?` and the stock-check query) each show a recovered `execute_tool` retry, same shape as Step 01
- [ ] Traces with 2 routed domains (SKU-002/003/004/005 ambiguous queries) show 2 specialist `invoke_agent` spans each
- [ ] Within ~1 minute, all 12 traces pick up an `orchestration_correctness` feedback score from Step 02's rule

Proceed to `04_failure_detection/`.
