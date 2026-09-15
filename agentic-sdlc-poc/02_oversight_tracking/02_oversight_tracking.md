# Step 02 — Human Oversight Tracking: UI Checklist

**Docs:** [Log traces](https://www.comet.com/docs/opik/v1/tracing/log_traces/), [OpenTelemetry](https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/), [Online evaluation rules](https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/)

Run `python 02_oversight_tracking/02_oversight_tracking.py`, then verify in Opik UI > Projects > `agentic-sdlc` > Traces.

- [ ] The same 12 threads from Step 01 reappear (new thread IDs — a fresh run — but the same session mix)
- [ ] In the Spans table's filter panel, add a **Custom filter** chip (key rooted at `input`, not `metadata`) with key `input.github.copilot.edit.accepted` = `false`; confirm it returns only `applyPatch` `execute_tool` spans, matching the script's `rejected_edit` total
- [ ] Add a **Custom filter** chip with key `input.github.copilot.feedback.vote` = `down`; confirm it returns only `chat` spans, matching the script's `negative_feedback` total
- [ ] Add a **Custom filter** chip with key `input.github.copilot.hook.decision` = `ask`; confirm it returns only `execute_hook` spans (all with `input.github.copilot.hook.name` = `Stop`), matching the script's `hook_confirmation_required` total
- [ ] These attributes live in each span's **`input`** field, not `metadata` — none of them match a GenAI/General OTel mapping rule on the backend, so use the UI's "Custom filter" chip rather than the plain `Metadata` filter chip
- [ ] Opening the `AUTH-101` thread shows 5 traces in order: `specify`, `plan`, `tasks`, `implement`, `implement` — the two `/implement` turns ARE the `rerun` event the script counts for that session
- [ ] No trace or span anywhere shows a `team` or `developer` field — this script's printed `dev=...` labels come from its own local `SESSIONS` list, never from Opik
- [ ] The script's printed **breakdown by driver category** (rejected_edit / negative_feedback / hook_confirmation_required / rerun counts) matches what filtering each attribute individually in the UI shows
- [ ] The script's printed **breakdown by session** is consistent with manually opening the 2-3 highest-count sessions and counting matching spans/reruns in their threads
- [ ] The script's printed **breakdown by team** queries each session's `github.copilot.git.repository` back from `trace.input` and joins it against `repo_team_map.py` — not a raw Opik field. Cross-check by filtering `input.github.copilot.git.repository = "<repo>"` for one team's repositories and summing events by hand.
- [ ] The **DEVELOPER BREAKDOWN: NOT AVAILABLE** callout prints before the event breakdowns

## Server-side detection — the online rule

- [ ] A rule named `edit-accepted` appears under this project's automation rules — **trace-level**, filter `name = invoke_agent`, enabled, sampling rate 100%
- [ ] The rule's type is `user_defined_metric_python`, not `llm_as_judge` — this is deterministic span-walking/counting, not a judgment call
- [ ] The rule's `arguments` map shows the reserved `spans: spans` key (not a dotted trace-field path) — confirms it requested the trace's full span tree
- [ ] Confirm the `edit_accepted` feedback score appears in the UI (Traces tab > open a recent `invoke_agent` trace > Feedback scores panel), for all three cases:
  - [ ] An `implement` turn whose `applyPatch` span has `edit.accepted = True` shows `edit_accepted = 1.0`
  - [ ] A `specify`/`plan`/`tasks` turn (no `applyPatch` span) shows `edit_accepted = 1.0`, reason stating "No edits occurred in this turn"
  - [ ] An `implement` turn whose `applyPatch` span has `edit.accepted = False` shows `edit_accepted = 0.0`
- [ ] The rule only scores traces logged **after** its creation — it does not retroactively score the batch of sessions run earlier in the same script invocation
- [ ] If nothing appears after ~1 minute on a NEW session, check
  `client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id=<rule_id printed by the script>)` before assuming the rule is broken
- [ ] **Known limitation:** if an `implement` turn's `edit_accepted` score reads `1.0`/"No edits occurred" even though that trace clearly has an `applyPatch` span, this is the documented OTLP-batch-ingestion timing issue (see `02_oversight_tracking.py`'s module docstring), not a rule bug — cross-check via the Spans tab, or re-run and inspect a fresh trace.

Proceed to `03_risk_governance/`.
