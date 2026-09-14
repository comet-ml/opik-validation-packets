# Step 02 — Online Evaluation Rules: UI Checklist

**Docs:** [Online evaluation rules](https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/)

Run `python 02_online_eval/02_online_eval.py`, then verify in Opik UI > Projects > `multi-agent-orchestration-poc` > Rules (or Online Evaluation).

- [ ] A rule named `orchestration-correctness` appears — trace-level, filter `name = orchestrator_run`
- [ ] A rule named `context-relevance` appears — **span-level**, filter `name = execute_tool search_incident_reports`
- [ ] A rule named `rag-groundedness` appears — trace-level, filter `tags contains anomaly`
- [ ] All three are enabled, sampling rate 100%

This step only configures the rules — they have nothing to score yet. Proceed to
`03_simulation/03_simulation.py` to generate traffic, then come back here to confirm:

- [ ] New `orchestrator_run` traces from Step 03 show an `orchestration_correctness` feedback score (may take up to ~1 minute to appear — online scoring is asynchronous), on both single-domain and ambiguous/multi-domain traces
- [ ] Only the SKU-003/SKU-005 (anomaly-routed) traces additionally show a `rag_groundedness` score — the other domains never call `search_incident_reports`, so they have no retrieved context for this rule to judge
- [ ] The `execute_tool search_incident_reports` **span itself** (not the trace) shows a `context_relevance` feedback score — this is scored directly on that one span's input/output, independent of the trace-level rules

If nothing appears after a few minutes, check a rule's execution logs via
`client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id=...)` — printed by
`02_online_eval.py` on creation — before assuming the rule is broken; this API surface has no
existing examples/tests in the Opik SDK repo, so treat a first live run as exploratory.

**Why context-relevance is span-level and rag-groundedness isn't:** span-level rules can only see
that ONE span's own input/output/metadata — confirmed against the backend source
(`OnlineScoringEngine.toReplacements(variables, Span)`) that there's no path to a sibling span or
the parent trace. Context relevance only needs the retrieval span's own input (query) and output
(retrieved text), so it fits span-level cleanly with zero trace-output plumbing. Groundedness needs
BOTH the retrieved context (on the retrieval span) AND the final answer (on a different span) —
structurally impossible at span level, so it stays trace-level, reading both via
`orchestrator.py`'s `retrieved_context`/`specialist_responses` trace-output fields.

**Gotcha found live:** the dotted-path `variables` resolution (`output.foo.bar` → JSONPath) breaks
when a JSON key's NAME itself contains literal dots — exactly what
`agent_framework`'s own span fields look like (`gen_ai.tool.call.arguments`, one key, not four
nested levels). `context-relevance`'s `variables` therefore maps the whole `input`/`output` section
instead of a dotted sub-path, with the prompt telling the judge which literal key to read.

**Product-gap note:** none of these three rules is a true "standard metric, zero custom-building"
configuration — Opik's online-rule API only supports `llm_as_judge` (a prompt you write) or
`user_defined_metric_python` (code you write); there's no way to select one of the SDK's built-in
metric classes (Hallucination, ContextPrecision, TrajectoryAccuracy, ...) by name for live scoring,
even though those classes exist and work fine offline via `opik.evaluate()`. `rag-groundedness`'s
prompt is adapted as closely as possible from Opik's real `Hallucination` metric template to
partially close that gap, but it's still hand-authored, not selected.

Proceed to `03_simulation/03_simulation.py`.
