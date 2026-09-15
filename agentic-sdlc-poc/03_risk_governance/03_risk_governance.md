# Step 03 — Governance & Risk Monitoring: UI Checklist

**Docs:** [Online evaluation rules](https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/), [Log traces](https://www.comet.com/docs/opik/v1/tracing/log_traces/)

> **This step is a discussion point, not a settled recommendation.** It turns
> `capture_content=True` on for the first time in this packet — a real,
> all-or-nothing tradeoff (Copilot's enterprise `captureContent` toggle has no
> per-field granularity). It demonstrates that a governance-relevant risk
> category (sensitive data in prompts) is trackable and reportable in Opik —
> it does NOT recommend turning this on in production. Whether/how to do so,
> and the full risk taxonomy beyond this one worked example, is a decision
> for the customer's own governance/security stakeholder.

Run `python 03_risk_governance/03_risk_governance.py`, then verify in Opik UI > Projects > `agentic-sdlc`.

## Client-side detection

- [ ] The script's console output shows a callout that content capture is turning on for the first time, framed as a capability for discussion — not a default flip
- [ ] 4 new threads appear (Threads tab): `SEC-201` (the deliberately-injected risk scenario) plus `PROJ-101`, `INV-205`, `PORT-042` (normal, false-positive contrast)
- [ ] Open the `SEC-201` thread's `specify` trace > `chat` span. Its **`input`** field shows a literal key `gen_ai.prompt` containing the full prompt text — including the fabricated `api_key=sk-abc123DEFghijKLMnop456QRS789` string verbatim (planted in `spec_kit_artifacts.TICKETS`'s `SEC-201` description)
- [ ] That same `chat` span's **`output`** field shows a literal key `gen_ai.completion` — the model's generated spec.md, which also echoes the fake key back
- [ ] An `execute_tool` span on any trace shows `input["gen_ai.tool.call.arguments"]` as a real nested JSON object (not a string) and `output["gen_ai.tool.call.result"]` as a plain string
- [ ] The script's own printed client-side scan shows `SEC-201` with several findings (`openai_api_key` + `generic_api_key_assignment` categories) and **zero** findings on `PROJ-101`/`INV-205`/`PORT-042`
- [ ] No trace/span anywhere shows `gen_ai.prompt`/`gen_ai.completion`/`gen_ai.tool.call.arguments`/`gen_ai.tool.call.result` for sessions from Steps 01/02 — those ran with `capture_content=False`

## Server-side detection — the online rule

- [ ] A rule named `sensitive-data-in-prompt` appears under this project's automation rules — **span-level**, filter `name = chat`, enabled, sampling rate 100%
- [ ] The rule's type is `user_defined_metric_python`, not `llm_as_judge` — this is deterministic regex matching, not a judgment call
- [ ] The rule is created BEFORE the script's sessions run, so `SEC-201`'s own `chat` spans get a `sensitive_data_detected = 1.0` feedback score within the same run (no second run needed), with a `reason` naming the exact categories/matches
- [ ] The 3 normal sessions (`PROJ-101`, `INV-205`, `PORT-042`) score `sensitive_data_detected = 0.0` on every `chat` span
- [ ] If a score is still missing after ~1-2 minutes, check
  `client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id=<rule_id printed by the script>)` before assuming the rule is broken

## Gotchas to spot-check

- [ ] Filtering the Spans table by a **Custom filter** chip `input.gen_ai.prompt` (dictionary-style, not the plain `Metadata` chip) returns the `chat` spans with captured content — confirms these are literal top-level dotted keys, not nested JSON
- [ ] The rule's Python code (visible in the rule's detail view) is fully self-contained — no import of `risk_patterns.py` or any other file in this repo; the sandbox cannot reach local modules
- [ ] The rule's `arguments` map `prompt_section`/`completion_section` to the WHOLE `input`/`output` section (not a dotted sub-path like `input.gen_ai.prompt`) — the Python code itself does the `json.loads` + literal-key lookup

Proceed to `04_cost_roi/`.
