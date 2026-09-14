# Step 01 — Tracing: UI Checklist

**Docs:** [OpenTelemetry Python SDK](https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/)

Run `python 01_tracing/01_tracing.py`, then verify in Opik UI > Projects > `multi-agent-orchestration-poc` > Traces.

- [ ] 4 new traces appear, one per sample query
- [ ] Each trace's top-level span is named `orchestrator_run` (the single `@opik.track` boundary)
- [ ] Expanding a trace shows an `invoke_agent triage_agent` span nested directly under `orchestrator_run` — **this nesting is the proof the OTel bridge worked**: without `OpikSpanProcessor` registered (otel_setup.py), these spans would land in a separate, disconnected trace instead
- [ ] The SKU-001 and SKU-002 traces each show exactly ONE `invoke_agent <specialist>_agent` span alongside the triage/synthesis agents (single-domain routing)
- [ ] The SKU-003 trace shows TWO specialist `invoke_agent` spans (`inventory_agent` and `anomaly_agent`) — the ambiguous, multi-domain fan-out
- [ ] The SKU-004 trace's `invoke_agent forecast_agent` span shows TWO `execute_tool forecast_lookup` children: the first carries the simulated error, the second succeeds — the retry-recovery case, and it was the MODEL that decided to retry, not orchestrator code
- [ ] Each `invoke_agent` span contains `chat gpt-4o-mini` leaf spans with non-zero token usage
- [ ] Trace metadata/tags reflect `orchestration_framework: microsoft_agent_framework`

Proceed to `02_online_eval/02_online_eval.py`.
