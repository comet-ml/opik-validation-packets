"""
Step 02 — Online Evaluation Rules

Configures four Opik "online evaluation" rules — server-side automations
that score live traces/spans AS THEY ARRIVE — against this project:

    orchestration-correctness (trace-level) — every orchestrator_run trace:
        is the final answer faithful to ALL routed agent outputs, especially
        on ambiguous (multi-domain) queries. Contrast with
        genai-gateway-persona-poc's Step 04, which uses opik.evaluate()
        against a fixed offline dataset.

    context-relevance (SPAN-level) — every execute_tool
        search_incident_reports span: is the retrieved incident report
        actually relevant to the retrieval query? Scored directly on that
        one span's own input/output — no trace-level plumbing needed at all.

    rag-groundedness (trace-level) — only traces tagged "anomaly": is the
        specialist's final answer faithful to the incident report it
        retrieved? This one genuinely CANNOT be span-level: the retrieved
        context lives on the search_incident_reports span, but the final
        answer lives on a DIFFERENT span (invoke_agent anomaly_agent) —
        confirmed against the backend source
        (OnlineScoringEngine.toReplacements(variables, Span)) that
        span-scoped rule variables can only resolve against that ONE span's
        own input/output/metadata, never a sibling/parent/trace field. So
        this one still needs orchestrator.py to surface retrieved_context on
        the trace output, and its variables map into that trace-level JSON
        via dotted paths (output.retrieved_context.anomaly /
        output.specialist_responses.anomaly) — confirmed live to extract
        correctly.

    reliability-metrics (trace-level, PYTHON not LLM) — every orchestrator_run
        trace: how many tool calls failed (error_count) and how many of
        those recovered on a same-named sibling span (retry_count)? This is
        pure counting/arithmetic, not a judgment call, so it's a
        `user_defined_metric_python` rule, not an LLM prompt — deterministic,
        free, instant, no model to misjudge. Confirmed against the backend
        source that a TRACE-scoped Python metric can request the trace's
        full span tree via the reserved argument key `arguments={"spans":
        "spans"}` (spelled out in OnlineScoringUserDefinedMetricPythonScorer
        .java — the value is ignored, only the key matters), which arrives
        in Python as `spans: list[dict]` (nested children under each span's
        own "spans" key, snake_cased fields: name/type/input/output/
        metadata/error_info/...). Same underlying data
        05_retry_detection.py already computes client-side — this rule does
        it automatically, server-side, for every future trace, not just a
        batch a script happens to run.

context-relevance and rag-groundedness together cover exactly the two named
RAG-quality metrics from this use case's criteria ("context relevance,
groundedness") — decomposed into a single-span check (was the retrieval
itself good) and a cross-span check (was the generation faithful to what was
retrieved), which is the standard shape for this, not something exotic.

The first three are `llm_as_judge` rules (a server-side prompt, evaluated by
Opik's backend); reliability-metrics is `user_defined_metric_python` (a real
Python class executed server-side — see GOTCHA 3 below for the actual
runtime contract, which is NOT a bare function). There is no high-level SDK
wrapper for rule management — only the generated REST client
(`client.rest_client.automation_rule_evaluators`), which as of this SDK
version has no examples or tests anywhere in the Opik repo. Treat this
script as exploratory: if a live run errors, check
`get_evaluator_logs_by_id` and the error body first (see the note printed at
the end of main()).

GOTCHA 1 (found live): `AutomationRuleEvaluatorWrite`'s `enabled` field
defaults to `None`/falsy — a rule created without explicitly passing
`enabled=True` is silently created DISABLED. It shows up fine via
`find_evaluators`, accepts traffic, and produces zero errors; the only signs
are `feedback_scores` never populating, and `get_evaluator_logs_by_id`
logging `"traceId ... was skipped ... as the rule is disabled"` for every
matching trace. Always check the logs before assuming a rule is broken some
other way.

GOTCHA 2 (found live): the dotted-path `variables` resolution
(output.foo.bar -> JSONPath $.foo.bar) breaks when the JSON itself has a key
whose NAME contains literal dots — which is exactly what
agent_framework's own OTel GenAI-semantic-convention span fields look like:
a tool span's input is `{"gen_ai.tool.call.arguments": {"query": ..., ...},
...}`, one key with dots in it, not four nested levels. A path like
`input.gen_ai.tool.call.arguments.query` silently resolves to nothing (the
judge gets an empty/missing value and the model fabricates a vague,
non-specific-sounding answer instead of erroring — verified live: swapped to
mapping the WHOLE input/output section instead (`variables={"query":
"input", "context": "output"}`) with the prompt itself telling the judge
which literal key to read, and the judge's reasoning immediately started
quoting the exact real query/retrieved text). context-relevance below uses
the whole-section form for this reason; rag-groundedness's trace-level
output doesn't have this problem since orchestrator.py controls those key
names directly (no dots in `retrieved_context`/`specialist_responses`).

GOTCHA 3 (found live): a `user_defined_metric_python` rule's `metric` string
is NOT a bare `def score(...)` function — the backend `exec()`s it as a
module and looks for a class subclassing `opik.evaluation.metrics.BaseMetric`
(`process_worker.py`'s `get_metric_class`), instantiates it with no
constructor args, and calls `.score(**arguments)`. It must return a
`ScoreResult` or `list[ScoreResult]` (imported from
`opik.evaluation.metrics.score_result` inside the submitted code itself) —
returning a plain float/dict fails. Sandbox is a real Docker container
(network disabled, 256MB, 3s exec timeout) with the stdlib available, not a
restricted eval — plain recursion/string comparison is fine.

TODO(SE) — real product gap, not something this packet can code around:
Opik ships built-in metric CLASSES for exactly this (TrajectoryAccuracy,
AgentTaskCompletionJudge, Hallucination, ContextPrecision, ...), but only for
OFFLINE opik.evaluate() runs. The online-rule REST API only supports two
types, `llm_as_judge` and `user_defined_metric_python` — there is no way to
reference a built-in metric CLASS by name for live scoring; you either write
a judge prompt or submit real Python source implementing the logic yourself
(reliability-metrics below is the latter — genuinely custom code, since
"count spans with error_info" has no built-in Opik equivalent regardless).
rag-groundedness's prompt is adapted from Opik's real Hallucination wording
to partially close that same gap for judge-based rules — not a true
"standard metric, zero custom-building" configuration.

Docs: https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/

Usage:
    python 02_online_eval/02_online_eval.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import opik
from opik.rest_api.types.automation_rule_evaluator_write import (
    AutomationRuleEvaluatorWrite_LlmAsJudge,
    AutomationRuleEvaluatorWrite_SpanLlmAsJudge,
    AutomationRuleEvaluatorWrite_UserDefinedMetricPython,
)
from opik.rest_api.types.llm_as_judge_code_write import LlmAsJudgeCodeWrite
from opik.rest_api.types.llm_as_judge_message_write import LlmAsJudgeMessageWrite
from opik.rest_api.types.llm_as_judge_model_parameters_write import LlmAsJudgeModelParametersWrite
from opik.rest_api.types.llm_as_judge_output_schema_write import LlmAsJudgeOutputSchemaWrite
from opik.rest_api.types.span_llm_as_judge_code_write import SpanLlmAsJudgeCodeWrite
from opik.rest_api.types.span_filter_write import SpanFilterWrite
from opik.rest_api.types.trace_filter_write import TraceFilterWrite
from opik.rest_api.types.user_defined_metric_python_code_write import UserDefinedMetricPythonCodeWrite

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")

ORCHESTRATION_CORRECTNESS_PROMPT = (  # TODO(SE): generic/illustrative rubric — replace with the real standard
    "You are reviewing a multi-agent demand-forecasting orchestrator's final answer.\n\n"
    "The orchestrator routed the user's query to one or more of: forecast_agent, "
    "inventory_agent, anomaly_agent. Their combined structured outputs and the "
    "orchestrator's final natural-language answer are captured below as JSON.\n\n"
    "{{output}}\n\n"
    "Score orchestration_correctness as 1 if the final answer (a) only states facts present in "
    "the agent outputs, and (b) addresses EVERY domain that was routed to (no "
    "dropped domain on an ambiguous/multi-domain query). Score 0 otherwise."
)

# Span-level — scored directly on the execute_tool search_incident_reports span.
# Whole-section variable mapping (not a dotted nested path) — see GOTCHA 2 above.
CONTEXT_RELEVANCE_PROMPT = (
    "This JSON is a single retrieval tool call.\n\n"
    "INPUT (contains the retrieval query under the key gen_ai.tool.call.arguments.query):\n"
    "{{query}}\n\n"
    "OUTPUT (contains the retrieved text under the key gen_ai.tool.call.result):\n"
    "{{context}}\n\n"
    "Score context_relevance as 1.0 if the retrieved text is relevant to the query, or 0.0 if "
    "it is off-topic or unrelated. In your reason, quote the specific query and retrieved text "
    "you evaluated."
)

# Trace-level — adapted from Opik's real Hallucination metric prompt (see module
# docstring) — guidelines 1-3 below are near-verbatim from that template's
# _CONTEXT_SYSTEM_PROMPT. {{context}}/{{answer}} are each mapped to their own
# nested trace field (no dotted-key collision here — orchestrator.py controls
# these key names directly).
RAG_GROUNDEDNESS_PROMPT = (
    "You are an expert judge evaluating the faithfulness of a RAG-grounded answer to its "
    "retrieved context.\n\n"
    "CONTEXT (the retrieved incident report):\n{{context}}\n\n"
    "OUTPUT (the specialist's answer to judge against it):\n{{answer}}\n\n"
    "Guidelines:\n"
    "1. The OUTPUT must not introduce new information beyond what's provided in the CONTEXT.\n"
    "2. The OUTPUT must not contradict any information given in the CONTEXT.\n"
    "3. Consider partial hallucinations where some information is correct but other parts "
    "are not.\n\n"
    "Score rag_groundedness as 1.0 if the OUTPUT is entirely faithful to the CONTEXT, or 0.0 "
    "if it is entirely or partially unfaithful."
)

# Trace-level, PYTHON (not a prompt) — real code executed server-side, must
# define exactly one class subclassing BaseMetric (see GOTCHA 3 above).
# "spans" arrives as the trace's full span tree (nested under each span's own
# "spans" key) because the rule below requests it via arguments={"spans": "spans"}.
RELIABILITY_METRIC_CODE = '''
from opik.evaluation.metrics import BaseMetric
from opik.evaluation.metrics.score_result import ScoreResult


class ReliabilityMetric(BaseMetric):
    def __init__(self, name: str = "reliability"):
        super().__init__(name=name)

    def _flatten(self, spans):
        flat = []
        for s in spans or []:
            flat.append(s)
            flat.extend(self._flatten(s.get("spans")))
        return flat

    def score(self, spans=None, **kwargs):
        all_spans = self._flatten(spans)
        tool_spans = [s for s in all_spans if (s.get("name") or "").startswith("execute_tool ")]

        by_name = {}
        for s in tool_spans:
            by_name.setdefault(s.get("name"), []).append(s)

        error_count = sum(1 for s in tool_spans if s.get("error_info"))
        retry_count = 0
        for name, group in by_name.items():
            failed = [s for s in group if s.get("error_info")]
            recovered = [s for s in group if not s.get("error_info")]
            if failed and recovered:
                retry_count += 1

        return [
            ScoreResult(
                name="error_count", value=float(error_count),
                reason=f"{error_count} tool call(s) with error_info across {len(tool_spans)} tool span(s)",
            ),
            ScoreResult(
                name="retry_count", value=float(retry_count),
                reason=f"{retry_count} tool(s) failed then recovered on a same-named sibling span",
            ),
        ]
'''

RULES = [
    {
        "level": "trace",
        "name": "orchestration-correctness",
        "score_name": "orchestration_correctness",
        "prompt": ORCHESTRATION_CORRECTNESS_PROMPT,
        "filters": [TraceFilterWrite(field="name", operator="=", value="orchestrator_run")],
        "description": "1 = faithful and complete, 0 = fabricated or dropped a routed domain",
        # Deliberately the whole output blob, not split fields — this rule judges
        # completeness ACROSS domains (did it address every routed one), which
        # needs the full picture (domains_routed + every specialist response +
        # the final answer) together, not a single context/answer pair.
        "variables": {"output": "output"},
    },
    {
        "level": "span",
        "name": "context-relevance",
        "score_name": "context_relevance",
        "prompt": CONTEXT_RELEVANCE_PROMPT,
        "filters": [SpanFilterWrite(field="name", operator="=", value="execute_tool search_incident_reports")],
        "description": "1.0 = retrieved report is relevant to the query, 0.0 = off-topic",
        "variables": {"query": "input", "context": "output"},
    },
    {
        "level": "trace",
        "name": "rag-groundedness",
        "score_name": "rag_groundedness",
        "prompt": RAG_GROUNDEDNESS_PROMPT,
        # Only traces where anomaly_agent actually ran have retrieved_context to judge —
        # see orchestrator.py's per-domain trace tags.
        "filters": [TraceFilterWrite(field="tags", operator="contains", value="anomaly")],
        "description": "1.0 = grounded in the retrieved incident report, 0.0 = hallucinated/contradicted it",
        "variables": {
            "context": "output.retrieved_context.anomaly",
            "answer": "output.specialist_responses.anomaly",
        },
    },
    {
        "level": "trace_python",
        "name": "reliability-metrics",
        "filters": [TraceFilterWrite(field="name", operator="=", value="orchestrator_run")],
        "code": RELIABILITY_METRIC_CODE,
        "arguments": {"spans": "spans"},  # reserved key — value is ignored, only the key matters
    },
]


def get_project_id(client: opik.Opik, name: str) -> str:
    page = client.rest_client.projects.find_projects(name=name)
    for project in page.content or []:
        if project.name == name:
            return project.id
    raise ValueError(f"Project {name!r} not found — run 01_tracing/01_tracing.py first so the project exists.")


def find_existing_rule(client: opik.Opik, project_id: str, name: str):
    found = client.rest_client.automation_rule_evaluators.find_evaluators(project_id=project_id, name=name)
    for rule in found.content or []:
        if rule.name == name:
            return rule
    return None


def ensure_rule(client: opik.Opik, project_id: str, config: dict) -> str:
    existing = find_existing_rule(client, project_id, config["name"])
    if existing:
        print(f"Rule {config['name']!r} already exists ({existing.id}) — skipping creation.")
        return existing.id

    common_kwargs = dict(
        project_ids=[project_id],
        name=config["name"],
        action="evaluator",
        enabled=True,  # NOT the default — a rule created without this is silently disabled
        sampling_rate=1.0,  # score every matching trace/span — TODO(SE): real sampling rate
        trigger_scope="production",
        filters=config["filters"],
    )
    if config["level"] == "span":
        rule = AutomationRuleEvaluatorWrite_SpanLlmAsJudge(
            **common_kwargs,
            code=SpanLlmAsJudgeCodeWrite(
                model=LlmAsJudgeModelParametersWrite(name="gpt-4o-mini", temperature=0),
                messages=[LlmAsJudgeMessageWrite(role="USER", content=config["prompt"])],
                variables=config["variables"],
                schema_=[LlmAsJudgeOutputSchemaWrite(
                    name=config["score_name"], type="DOUBLE", description=config["description"],
                )],
            ),
        )
    elif config["level"] == "trace_python":
        rule = AutomationRuleEvaluatorWrite_UserDefinedMetricPython(
            **common_kwargs,
            code=UserDefinedMetricPythonCodeWrite(
                metric=config["code"],
                arguments=config["arguments"],
            ),
        )
    else:
        rule = AutomationRuleEvaluatorWrite_LlmAsJudge(
            **common_kwargs,
            code=LlmAsJudgeCodeWrite(
                model=LlmAsJudgeModelParametersWrite(name="gpt-4o-mini", temperature=0),
                messages=[LlmAsJudgeMessageWrite(role="USER", content=config["prompt"])],
                variables=config["variables"],
                schema_=[LlmAsJudgeOutputSchemaWrite(
                    name=config["score_name"], type="DOUBLE", description=config["description"],
                )],
            ),
        )

    client.rest_client.automation_rule_evaluators.create_automation_rule_evaluator(request=rule)
    rule_id = find_existing_rule(client, project_id, config["name"]).id
    print(f"Created {config['level']}-level rule {config['name']!r} ({rule_id}).")
    return rule_id


def main():
    client = opik.Opik()
    project_id = get_project_id(client, OPIK_PROJECT_NAME)

    rule_ids = [ensure_rule(client, project_id, config) for config in RULES]

    print(
        "\nAll 4 rules are now live against this project. Run 03_simulation/03_simulation.py to "
        "generate traffic for them to score, then check a trace's (or, for context-relevance, a "
        "span's) feedback_scores in the UI (online scoring runs asynchronously — allow up to "
        "~1 minute)."
    )
    print(
        "Debug if nothing shows up: "
        f"client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id={rule_ids[0]!r})"
    )
    print("\nSee 02_online_eval.md for the UI checklist.")


if __name__ == "__main__":
    main()
