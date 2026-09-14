# Step 04 — Failure Detection: UI Checklist

Run `python 04_failure_detection/04_failure_detection.py`. The script itself queries the Opik API
and prints `[OK]`/`[MISSING]` for each injected failure — read its output first, then verify in the
UI using the two printed trace links:

- [ ] Console shows `[OK]` for both injected cases (2/2) — if either shows `[MISSING]`, the failure
  didn't get captured as expected; investigate before assuming the UI will show anything either
- [ ] **Transient case (SKU-004):** open its trace — the `execute_tool forecast_lookup` span appears
  TWICE under the same `invoke_agent forecast_agent` span: the first carries `error_info` (a real
  Python traceback), the second succeeds normally
- [ ] **Permanent case (SKU-000):** open its trace — `execute_tool forecast_lookup` also appears
  TWICE, but BOTH carry `error_info` with the identical error (the SKU doesn't exist, so retrying
  doesn't help) — and yet the trace's final `response` is a graceful natural-language message
  ("I'm unable to retrieve..."), not a crash
- [ ] In both cases, the failure is a real Python exception with a full traceback in `error_info` —
  not a made-up/asserted error, and not silently swallowed with no trace of it ever happening

This step demonstrates the difference between "recovered from a failure" (transient case) and
"gave up gracefully after a failure" (permanent case) — both leave the underlying problem fully
visible in Opik, which is the actual point: recovery or graceful degradation shouldn't mean losing
observability into what went wrong.

Proceed to `05_retry_detection/`.
