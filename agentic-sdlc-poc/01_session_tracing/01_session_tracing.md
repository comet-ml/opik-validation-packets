# Step 01 — Session Tracing: UI Checklist

**Docs:** [Log traces](https://www.comet.com/docs/opik/v1/tracing/log_traces/), [OpenTelemetry](https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/)

Run `python 01_session_tracing/01_session_tracing.py`, then verify in Opik UI > Projects > `agentic-sdlc` > Traces.

- [ ] 12 new threads appear (Threads tab), one per synthetic Spec-Kit session — thread ID looks like `sess-proj-101-xxxxxxxx`
- [ ] Opening the `AUTH-101` thread shows 5 traces in order: `specify`, `plan`, `tasks`, `implement`, `implement` (the two `/implement` turns model a human iterating after a first attempt)
- [ ] Opening the `INV-219` thread shows exactly ONE trace (`specify` only) — a session that stopped early
- [ ] Every trace's top-level span is named `invoke_agent` — the trace you see IS the `invoke_agent` OTel span, reconstructed purely server-side from the raw OTLP payload; there is no separate Opik SDK trace boundary anywhere in this harness
- [ ] A `specify` trace's `invoke_agent` span contains two `execute_tool` children (`readFile`, `grep`) before the `chat` child
- [ ] An `implement` trace's `invoke_agent` span contains, in order: `chat`, an `execute_hook` (`PreToolUse`/`allow`), then `execute_tool` (`applyPatch`) and `execute_tool` (`runTests`)
- [ ] The `applyPatch` `execute_tool` span carries a `github.copilot.edit.accepted` (true/false) attribute — the accept/reject signal, represented as a span attribute rather than an OTel metric (Opik's OTLP ingestion doesn't support metrics)
- [ ] At least one `chat` span carries a `github.copilot.feedback.vote` (`up`/`down`) attribute
- [ ] Every `chat` span shows non-zero token usage (`gen_ai.usage.input_tokens`/`output_tokens` under Usage)
- [ ] The `invoke_agent` span/trace does NOT show a populated `usage` field on the SPAN itself, even though `copilot_session.py` sets those attributes on it — expected: Opik's backend dedups usage between a span and any child that also reports usage (see README). The TRACE-level `usage` field is a separate rollup and IS populated — don't confuse the two.
- [ ] No span anywhere carries `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.tool.call.arguments`, or `gen_ai.tool.call.result` — every session in this step ran with `capture_content=False` (Step 03 turns this on)
- [ ] The trace's **`input`** field (NOT `metadata`) shows `github.copilot.git.repository`, `.branch`, `.commit_sha`, and `github.copilot.github.org`. Filter the Traces table by a **Custom filter** chip rooted at `input` (e.g. `input.github.copilot.git.repository = "identity-service"`), NOT the plain `Metadata` filter chip.
- [ ] Trace `metadata` shows only real Copilot schema fields: `gen_ai.operation.name`, `gen_ai.agent.name`, `thread_id`, `integration`. It does **NOT** show `team`, `developer`, `workflow_step`, `slash_command`, or `ticket_id` — none of those are real Copilot attributes.
- [ ] The script's own printed breakdowns match the UI:
  - **Repository** — filtering `input.github.copilot.git.repository = "identity-service"` should return the same count as the script's `identity-service` row.
  - **Team** — not a raw Opik field; the script joins the queried-back repository against `repo_team_map.py`. Cross-check by summing the repository counts for each team's repos by hand.
  - **Developer** — the script prints a callout that this is not achievable from Opik or real Copilot telemetry, and separately shows a harness-only breakdown labeled as such. Confirm there's genuinely no `developer` attribute anywhere in the UI.
  - **Workflow step** — also not a raw Opik field. The script classifies each trace as `implement` only if it contains an `applyPatch`/`runTests` span; `specify`/`plan`/`tasks` are indistinguishable from each other. Spot-check a couple of traces in the UI to confirm.

Proceed to `02_oversight_tracking/`.
