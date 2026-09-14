# Multi-Agent Orchestration PoC — Opik Validation Scripts

Validation scripts for a generic "multi-agent demand-forecasting orchestrator" use case: a real
Microsoft Agent Framework app (`agent-framework-core` + `agent-framework-openai`, OpenAI only) that
routes a user's supply-chain question to one or more of 3 specialist agents (`forecast_agent`,
`inventory_agent`, `anomaly_agent`), recovers from a simulated transient tool failure via the
model's own retry, and fans out to every relevant specialist when a query is ambiguous (spans more
than one domain). Work through the numbered steps in order — each step consumes artifacts produced
by the previous ones (the live project, the online eval rule, etc.) rather than being disconnected
scripts.

Everything is offline/dev-scoped against synthetic data — see each step's `# TODO(SE):` markers
showing exactly where a real solutions engineer would swap in the real customer's specifics. This
packet is intentionally independent of the "Traditional ML / predictive modeling" PoC: the SKU
forecast/inventory/anomaly data here is synthetic and schema-similar in shape to what a real
forecasting model would output, but the two are not wired together.

This packet is scoped to 6 steps, not the 8 in `genai-gateway-persona-poc` — the customer's stated
concerns for this use case (orchestration correctness, ambiguity handling, retry recovery) are
about **live production traffic**, not an offline golden-dataset benchmark, so it centers on
tracing + online evaluation rather than datasets/experiments/regression-gating.

## The app

| Component | Role |
|---|---|
| `orchestrator.py` | A real triage `Agent` (LLM-driven tool-calling, not a keyword classifier) decides which specialist(s) apply, dispatches to them directly, then a synthesis `Agent` composes the final answer. Single `@opik.track` boundary (`run_forecast_query`). |
| `agents.py` | The 3 specialist agents (`forecast_agent`, `inventory_agent`, `anomaly_agent`) — each a real `agent_framework.Agent`. `forecast_agent`/`inventory_agent` each have one structured-lookup `@tool`; `anomaly_agent` has that PLUS a real RAG tool, `search_incident_reports` (keyword-overlap retrieval over a synthetic incident-report corpus), so it can ground its explanation in an actual retrieved document. |
| `otel_setup.py` | Points Microsoft Agent Framework's own real OpenTelemetry auto-instrumentation at Opik's OTLP endpoint and layers `OpikSpanProcessor` on top. |
| `data_store.py` | Loads the synthetic SKU records (`data/domain_data.json`) and the incident-report corpus (`data/incident_reports.json`). |

**Microsoft Agent Framework has no native Opik SDK integration** (unlike LangGraph/CrewAI/DSPy/
etc.) — but it DOES ship its own real OpenTelemetry auto-instrumentation
(`agent_framework.observability`), which emits a full span tree for every `Agent.run()` call with
**zero manual span-wrapping code** (verified live: one call with one tool produces
`invoke_agent -> chat -> execute_tool -> chat` automatically). `otel_setup.py` points that
instrumentation's OTLP exporter at Opik and registers `OpikSpanProcessor` so those spans thread
onto the Opik-native trace opened by the single `@opik.track` boundary — see its module docstring
and `orchestrator.py`'s for the full picture, including why
`agent_framework_orchestrations.HandoffBuilder` (the framework's own decentralized multi-agent
routing builder) was tried and rejected: live-tested against real OpenAI, it looped 35+ turns
without converging to one answer — its conversational/autonomous-continuation design targets
open-ended chat, not a bounded single-answer-per-query flow.

**Retry is real, not hand-rolled.** `agents.py`'s `FLAKY_SKUS` makes a tool raise once per
(tool, sku); Microsoft Agent Framework's own function-invocation loop catches that exception, feeds
an error message back to the model, and each specialist's instructions ("if your tool call fails,
try it again exactly once") make the MODEL decide to retry — verified live: the tool was called
twice within one `agent.run()`, which returned normally. This shows up in the trace as two
`execute_tool` spans, the first carrying the error.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in COMET_API_KEY / OPIK_WORKSPACE / OPENAI_API_KEY in .env
```

`.env` holds secrets only (Opik + OpenAI API keys/workspace, plus `OPIK_URL_OVERRIDE` for a
single-tenant instance). Everything else project-specific — the project name, the agent
instructions/model, etc. — is hardcoded as plain constants directly in whichever file uses it (no
shared config module). Each entrypoint script (or `otel_setup.py`, which every entrypoint imports
transitively) starts with the same two lines: `load_dotenv()`, then
`os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")`, since the SDK only ever reads
`OPIK_API_KEY` but the shared credentials file stores the key under `COMET_API_KEY`.

Every agent call is async (`Agent.run()` is a coroutine) — each step script's `main()` is `async`
and run via `asyncio.run(main())`.

## Running

| Step | Script(s) | Checklist |
|------|-----------|-----------|
| 01 | `01_tracing/01_tracing.py` — exercise the orchestrator, confirm the OTel-bridged merged trace shape | `01_tracing/01_tracing.md` |
| 02 | `02_online_eval/02_online_eval.py` — create the `orchestration_correctness` (trace), `context_relevance` (span), and `rag_groundedness` (trace) online evaluation rules against this project | `02_online_eval/02_online_eval.md` |
| 03 | `03_simulation/03_simulation.py` — run a 12-query synthetic traffic batch (single-domain, ambiguous, and retry cases) for all three rules to score | `03_simulation/03_simulation.md` |
| 04 | `04_failure_detection/04_failure_detection.py` — inject a transient (self-healing) and a permanent (non-recoverable) failure; programmatically confirm both are visible in their traces via the Opik API | `04_failure_detection/04_failure_detection.md` |
| 05 | `05_retry_detection/05_retry_detection.py` — run a 5-query batch (3 retry-triggering, 2 control) and programmatically count retry events per trace | `05_retry_detection/05_retry_detection.md` |
| 06 | `06_dashboard/seed_historical_data.py` then `06_dashboard/06_dashboard.py` | `06_dashboard/06_dashboard.md` |

Each step also has real UI checklists in its `.md` file. Verified live end-to-end against real
OpenAI + Opik: Step 01's 4 sample queries and Step 03's 12-query batch all routed correctly
(12/12 on the last two live runs), the SKU-004 retry recovering as designed, a real anomaly query
correctly grounding its answer in a retrieved incident report, all three online eval rules (one
span-level) scoring with genuine, specific reasons, both Step 04 failure injections confirmed
visible via the API (2/2), and Step 05's retry detection matching expected behavior on all 5
queries (3/3 real retries found, 2/2 controls correctly showing none).

## Before running with a real customer

Search this repo for `# TODO(SE):` — every one marks a spot with a real agent registration / real
routing instructions / real rubric wording / a config value to swap in once the real customer's
specifics are known (start with `orchestrator.py` for the triage/synthesis instructions, `agents.py`
for the specialist instructions and model, and `02_online_eval/02_online_eval.py` for the judge
rubric).

## Online evaluation rules

`02_online_eval.py` creates three `llm_as_judge` rules, sampling 100%:

- **orchestration_correctness** (trace-level) — scoped to `orchestrator_run` traces: does the final
  answer only state facts present in the routed agent outputs, and does it address every domain
  routed to on an ambiguous query?
- **context_relevance** (**span-level**) — scoped directly to the `execute_tool
  search_incident_reports` span: is the retrieved incident report actually relevant to the
  retrieval query? Judged on that one span's own input/output — no trace-level plumbing at all.
- **rag_groundedness** (trace-level) — scoped to traces tagged `anomaly`: is the specialist's final
  answer faithful to the incident report it retrieved? This one genuinely can't be span-level — the
  retrieved context lives on one span, the final answer on a different one, and a span-scoped rule
  can only see that single span's own fields (confirmed against the backend source — no path to a
  sibling span or the parent trace). So it stays trace-level, reading both via `orchestrator.py`'s
  `retrieved_context`/`specialist_responses` trace-output fields via dotted JSONPath variables.

`context_relevance` + `rag_groundedness` together are exactly the two RAG-quality metrics named in
this use case's criteria ("context relevance, groundedness") — decomposed into a single-span check
(was the retrieval good) and a cross-span check (was the generation faithful to it), which is the
standard shape for this, not something exotic.

All three verified live end-to-end: a real anomaly query correctly retrieved `[INC-2031]`/`[INC-2032]`,
grounded its answer in it, and all three rules scored with a genuine, specific per-score reason
(not a generic/hallucinated-sounding one — see the JSONPath gotcha below, which was caught exactly
because an early version's reasoning was suspiciously vague).

There is no high-level SDK wrapper for rule management (only the generated REST client,
`client.rest_client.automation_rule_evaluators`) — treat a first live run of this step as
exploratory; see its docstring for how to pull a rule's execution logs if nothing scores. Two real
gotchas found this way:

- `AutomationRuleEvaluatorWrite`'s `enabled` field defaults to falsy — a rule created without
  explicitly passing `enabled=True` is silently created disabled (no error, it just never scores
  anything; `get_evaluator_logs_by_id` is what surfaces this).
- The dotted-path `variables` resolution (`output.foo.bar` → JSONPath) breaks when a JSON key's
  NAME itself contains literal dots — exactly what `agent_framework`'s own span fields look like
  (`gen_ai.tool.call.arguments` is one key, not four nested levels). `context_relevance` maps the
  whole `input`/`output` section instead, with the prompt telling the judge which literal key to
  read, rather than a dotted sub-path.

**Product-gap note:** neither rule is a true "standard metric, zero custom-building" configuration.
Opik ships built-in metric classes for exactly this (`TrajectoryAccuracy`, `AgentTaskCompletionJudge`,
`Hallucination`, `ContextPrecision`, ...), but only for offline `opik.evaluate()` runs — the
online-rule REST API only supports `llm_as_judge` or `user_defined_metric_python`, with no way to
select a built-in metric by name for live scoring. Worth a Jira ticket if this matters to the
customer's actual requirement.

## Known limitations (this environment)

- Some Opik Cloud workspace tiers enforce a 24-hour ingestion window on backdated trace IDs. If
  `06_dashboard/seed_historical_data.py` fails with `reason 'too_old'`, lower `DAYS_BACK` in that
  file or check your workspace's historical-ingestion allowance.
- The `agents.py` retry simulation (`FLAKY_SKUS`) only fails once per (tool, SKU) pair for the life
  of the Python process — re-running a step against the same SKU in the same process will not
  re-trigger the failure. This is enough to demonstrate the retry path once per run (each numbered
  step is its own process, so Steps 01/03/04/05 each get a fresh failure on SKU-004 independently).
- Routing is now a real LLM call (`triage_agent`), not a deterministic keyword match — expect
  occasional run-to-run variance rather than a guaranteed 100% `routing_accuracy` in Step 03. That
  variance is realistic and is exactly what the Step 02 online-eval rules exist to catch.
- `search_incident_reports`' keyword-overlap retrieval (top_k=2) can pull in a second, less-relevant
  document alongside the correct one — real retrieval imperfection, not a bug, and not something the
  `rag_groundedness` judge penalizes (it checks the OUTPUT doesn't introduce facts absent from the
  CONTEXT, not that every retrieved document was used).
- `otel_setup.py` builds its own `OTLPSpanExporter` and passes it via
  `configure_otel_providers(exporters=[...])` rather than that function's own `otlp_endpoint=`
  param — the latter unconditionally also creates a metric and a log exporter, and Opik's OTLP
  ingest only implements the traces endpoint, so those two just fail with 404 on every flush.
- Dashboard latency/token breakdowns are keyed on real Microsoft Agent Framework span names
  (`invoke_agent`, `chat gpt-4o-mini`, `execute_tool`), not custom names.
