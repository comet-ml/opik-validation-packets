# Step 05 — Retry Detection: UI Checklist

Run `python 05_retry_detection/05_retry_detection.py`. The script itself queries the Opik API and
prints `[OK]`/`[MISMATCH]` per query plus a total retry-event count — read its output first.

- [ ] Console shows `5/5` queries matched expected retry behavior
- [ ] Console reports exactly `3` total retry events (one per SKU-004 specialist tool: `forecast_lookup`, `inventory_lookup`, `anomaly_lookup`) — the 2 control queries (SKU-001, SKU-002) contribute zero
- [ ] Open one of the SKU-004 traces — confirm the retry is visually obvious: two `execute_tool` spans with the same name back-to-back, the first red/errored, the second normal
- [ ] Open one of the control traces (SKU-001/SKU-002) — confirm exactly one `execute_tool` span, no error

This turns "review traces for retry patterns" into an actual measurable, repeatable check rather
than a manual UI skim — the retry-detection logic (`find_retry_events` in `05_retry_detection.py`)
is the kind of query a real monitoring job would run on a schedule against production traffic.

**Scope note:** this step demonstrates retries caused by a transient backend failure (matching
Step 04's first case). It does NOT demonstrate the "ambiguous prompt causes the agent to loop"
half of this criterion — that failure mode was observed once, live, while evaluating
`agent_framework_orchestrations.HandoffBuilder` (35+ turns without converging — see
`orchestrator.py`'s module docstring) and deliberately engineered out of the final design in favor
of a bounded, reliable triage-then-dispatch flow. A true looping demo would need a different,
less-reliable orchestration pattern than the one this packet intentionally uses.

Proceed to `06_dashboard/`.
