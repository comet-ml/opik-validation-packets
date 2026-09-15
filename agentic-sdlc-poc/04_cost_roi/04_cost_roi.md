# Step 04 — Cost & ROI Visibility: UI Checklist

**Docs:** [Log traces](https://www.comet.com/docs/opik/v1/tracing/log_traces/), [OpenTelemetry](https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/)

Run `python 04_cost_roi/04_cost_roi.py`, then verify in Opik UI > Projects > `agentic-sdlc` > Traces.

## Token usage — where the real numbers come from

- [ ] Open any `chat` span from one of this run's 7 sessions — its **Usage** panel shows non-zero `prompt_tokens`/`completion_tokens`/`total_tokens`. This is the number the script reads, not a value it invents.
- [ ] Open that same turn's `invoke_agent` (root) span — its **Usage** panel is empty, even though `copilot_session.py` sets the identical usage attributes on it. This is expected (see the README): the backend nulls a span's own usage whenever it's the direct parent of a usage-bearing child, which `invoke_agent` always is here.
- [ ] Open the trace itself (not a span) — the trace-level **Usage** field IS populated, and matches the `chat` span's usage exactly. Cross-check against the script's own printed "LIVE VERIFICATION" section, which asserts this for every trace in the run.
- [ ] Confirm the script's `LIVE VERIFICATION` section printed no MISMATCH lines.

## Cost — real tokens, manually estimated dollars

- [ ] Open a `chat` span's details panel and look for a **Total estimated cost** field — it should be empty or $0.00. Opik's cost lookup requires both a `model` and a `provider` attribute, and this harness (faithfully matching real Copilot's schema) only ever sets a model, never a provider. That's why this script computes a manual dollar estimate instead.
- [ ] The script's printed **cost breakdown by repository** table should have 4 rows (`identity-service`, `inventory-service`, `retail-order-service`, `internal-reporting-portal`) — cross-check each repository's turn count with a **Custom filter** chip: `input.github.copilot.git.repository = "<repo>"`.
- [ ] The script's printed **cost breakdown by team** table should have 4 rows matching `repo_team_map.py`'s mapping — not a raw Opik field, cross-check by summing each team's repositories from the breakdown above.
- [ ] Every dollar figure is labeled `~$` and "(APPROXIMATE)" — this is never presented as an exact GitHub billing figure.
- [ ] Spot-check the arithmetic on one row by hand: `cost = (input_tokens / 1_000_000) * 0.15 + (output_tokens / 1_000_000) * 0.60`.

## Developer-level cost breakdown — explicit dead end

- [ ] The `DEVELOPER-LEVEL COST BREAKDOWN: NOT AVAILABLE` callout prints before the per-developer table
- [ ] Confirm there is genuinely no `developer` attribute anywhere in the UI on any trace or span from this run
- [ ] The per-developer table is explicitly labeled `[HARNESS-ONLY grouping, tokens real]` — confirm the token/cost numbers match the same underlying chat-span data as the repository breakdown, even though the "grouped by developer" framing itself isn't reproducible from Opik

## The ROI-metric gap

- [ ] The `ROI METRIC: SHAPE PROPOSED, COST HALF CALCULATED, RETURN-SIGNAL HALF OUT OF SCOPE` section prints as a first-class part of the output — confirm it states plainly: cost signal built and real; return signal (delivery outcomes) out of scope; proposed shape is `return_signal(session) / cost_usd(session)`; `edit_accepted` (Step 02's rule) is named as a plausible future return-signal candidate, not implemented here
- [ ] Confirm no single "ROI score" number is printed anywhere in the output — only the cost half is calculated

Proceed — this is the last built step in this packet.
