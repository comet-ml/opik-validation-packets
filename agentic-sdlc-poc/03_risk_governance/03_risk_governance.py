"""
Step 03 — Governance & Risk Monitoring

Validates that at least one governance-relevant risk category (sensitive
data in prompts) is trackable and reportable in Opik.

============================================================================
THIS IS A DISCUSSION POINT, NOT A SETTLED RECOMMENDATION.
============================================================================
Everything below runs with `capture_content=True` — the first time anywhere
in this packet that content capture is turned on (Steps 01/02 ran with it
off). This is a real, all-or-nothing tradeoff:

  * Real GitHub-managed Copilot OTel export ships `capture_content` as a
    single enterprise-wide on/off toggle. There's no granular per-field
    control — no "capture tool arguments but not chat prompts."
  * Turning it on to DETECT sensitive data in prompts means first accepting
    that the same proprietary code, credentials, and internal context that
    might leak into a prompt also now flows into the telemetry pipeline in
    full — detection and exposure are the same lever.
  * This step demonstrates a capability: given captured content, Opik can
    surface a sensitive-data-in-prompt signal both client-side and
    server-side (a live online-evaluation rule). It does not recommend
    turning `capture_content` on in production. Whether/how to do so, and
    what the full risk taxonomy beyond this one worked example should be, is
    a decision for the customer's own governance/security stakeholder.

WHERE CONTENT ATTRIBUTES LAND:

    chat span:
        input["gen_ai.prompt"]        <- literal dotted key, NOT a nested
                                          path (input.gen_ai.prompt resolves
                                          to nothing)
        output["gen_ai.completion"]   <- same shape, in output

    execute_tool span:
        input["gen_ai.tool.call.arguments"]   <- parsed into a nested JSON
                                                  object automatically
        output["gen_ai.tool.call.result"]     <- plain string

Because the fabricated secret is baked directly into `SEC-201`'s ticket
description, it shows up in both the prompt and the completion once the
model echoes it back.

GOTCHA — `gen_ai.prompt`/`gen_ai.completion` are stored as single top-level
keys literally named "gen_ai.prompt"/"gen_ai.completion" inside the span's
`input`/`output` JSON, not as nested `{"gen_ai": {"prompt": ...}}`. Both the
client-side query code below and the online rule's Python metric read these
as literal dict keys after parsing — never as a dotted path. The online
rule's own `arguments` mapping maps the whole `input`/`output` section to a
variable rather than attempting a dotted sub-path, which would silently
resolve to nothing.

WHAT THIS SCRIPT DOES:

  1. Runs a small batch with `capture_content=True`: the `SEC-201` session
     (the deliberately-injected risk scenario) plus 3 normal sessions as a
     false-positive contrast check — do ordinary Spec-Kit sessions also trip
     the sensitive-data detector? They should not.
  2. Queries back every `chat`/`execute_tool` span's captured content and
     runs `risk_patterns.scan_for_sensitive_data()` over it client-side,
     printing findings per session.
  3. Deploys a real Opik online-evaluation rule — a span-scoped
     `user_defined_metric_python` rule, filtered to span name `chat` (content
     lives on `chat`/`execute_tool` spans specifically, so this must be
     span-level, not trace-level) — so future Copilot chat turns get scored
     automatically, server-side. The rule's Python code is a self-contained
     reimplementation of `risk_patterns.py`'s regex logic, since the sandbox
     can't import this repo's local modules.

A rule created without `enabled=True` is silently disabled — passed
explicitly here. The submitted `metric` string is exec'd as a module; it
must define a class subclassing `opik.evaluation.metrics.BaseMetric`,
instantiated with no constructor args, whose `.score(**arguments)` returns a
`ScoreResult`.

Docs: https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/

Usage:
    python 03_risk_governance/03_risk_governance.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import opik
from opik.rest_api.types.automation_rule_evaluator_write import (
    AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython,
)
from opik.rest_api.types.span_filter_write import SpanFilterWrite
from opik.rest_api.types.span_user_defined_metric_python_code_write import (
    SpanUserDefinedMetricPythonCodeWrite,
)

from copilot_session import flush, run_copilot_session, OPIK_PROJECT_NAME
from risk_patterns import scan_for_sensitive_data
from spec_kit_artifacts import DEVELOPERS, TICKETS

_TICKETS_BY_ID = {t["ticket_id"]: t for t in TICKETS}

# (ticket_id, developer, is_injected_risk) — the FIRST session is the
# deliberately-injected risk scenario (SEC-201, see spec_kit_artifacts.py);
# the other 3 are ordinary Spec-Kit sessions reused from Steps 01/02's own
# SESSIONS list, run here purely as a false-positive contrast check: do
# routine pagination/caching/CSV-export tickets ALSO trip the detector?
# All 4 run the full /specify -> /plan -> /tasks -> /implement sequence with
# capture_content=True — the first and only place in this packet that
# happens (see the loud module docstring above for why that's a real
# tradeoff, not a default flip).
SESSIONS = [
    ("SEC-201", DEVELOPERS[0], True),
    ("PROJ-101", DEVELOPERS[1], False),
    ("INV-205", DEVELOPERS[2], False),
    ("PORT-042", DEVELOPERS[3], False),
]

_CONTENT_SPAN_NAMES = {"chat", "execute_tool"}


def _captured_text(span) -> str:
    """Pull the actual captured prompt/completion/tool-argument/tool-result
    text off one span, reading the literal dotted keys these attributes
    land under (see module docstring — NOT a nested path)."""
    span_input = span.input or {}
    span_output = span.output or {}
    parts = []
    if span.name == "chat":
        parts.append(str(span_input.get("gen_ai.prompt", "")))
        parts.append(str(span_output.get("gen_ai.completion", "")))
    elif span.name == "execute_tool":
        # gen_ai.tool.call.arguments auto-parses into a real nested dict
        # (the attribute value looked like JSON) — serialize it back to
        # text for the regex scan; gen_ai.tool.call.result stays a string.
        parts.append(json.dumps(span_input.get("gen_ai.tool.call.arguments", {})))
        parts.append(str(span_output.get("gen_ai.tool.call.result", "")))
    return " ".join(p for p in parts if p)


# ============================================================================
# Online rule — real, span-scoped, user_defined_metric_python. `arguments`
# maps the WHOLE input/output section to a variable (a bare "input"/"output"
# path resolves to the whole section, JSON-serialized to a string) — the
# Python code below does its own json.loads + literal-key lookup.
# ============================================================================
SENSITIVE_DATA_METRIC_CODE = r'''
import json
import re

from opik.evaluation.metrics import BaseMetric
from opik.evaluation.metrics.score_result import ScoreResult

# Self-contained reimplementation of risk_patterns.py's regex logic — the
# online-rule sandbox cannot import this repo's local modules.
PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "generic_api_key_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}['\"]?"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "credit_card_like": re.compile(r"\b(?:\d[ -]?){12,15}\d\b"),
}


class SensitiveDataDetected(BaseMetric):
    def __init__(self, name: str = "sensitive_data_detected"):
        super().__init__(name=name)

    def _section_text(self, section, *literal_keys):
        # `section` arrives as the WHOLE input/output JSON section,
        # serialized to a string (see this file's arguments= mapping) —
        # parse it, then read the specific literal (dotted-name) key
        # ourselves.
        if not section:
            return ""
        if isinstance(section, str):
            try:
                parsed = json.loads(section)
            except (TypeError, ValueError):
                return section
        else:
            parsed = section
        if not isinstance(parsed, dict):
            return ""
        return " ".join(str(parsed.get(k, "")) for k in literal_keys)

    def score(self, prompt_section=None, completion_section=None, **kwargs):
        text = self._section_text(prompt_section, "gen_ai.prompt")
        text += " " + self._section_text(completion_section, "gen_ai.completion")

        hits = []
        for category, pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                hits.append(category + ":" + m.group(0))

        value = 1.0 if hits else 0.0
        if hits:
            reason = str(len(hits)) + " sensitive-data pattern match(es): " + ", ".join(hits[:5])
        else:
            reason = "No sensitive-data patterns matched in this chat span's captured prompt/completion."

        return ScoreResult(name="sensitive_data_detected", value=value, reason=reason)
'''


def get_project_id(client: opik.Opik, name: str) -> str:
    page = client.rest_client.projects.find_projects(name=name)
    for project in page.content or []:
        if project.name == name:
            return project.id
    raise ValueError(f"Project {name!r} not found — run 01_session_tracing/01_session_tracing.py first.")


def find_existing_rule(client: opik.Opik, project_id: str, name: str):
    found = client.rest_client.automation_rule_evaluators.find_evaluators(project_id=project_id, name=name)
    for rule in found.content or []:
        if rule.name == name:
            return rule
    return None


def ensure_sensitive_data_rule(client: opik.Opik, project_id: str) -> str:
    rule_name = "sensitive-data-in-prompt"
    existing = find_existing_rule(client, project_id, rule_name)
    if existing:
        print(f"Rule {rule_name!r} already exists ({existing.id}) — skipping creation.")
        return existing.id

    rule = AutomationRuleEvaluatorWrite_SpanUserDefinedMetricPython(
        project_ids=[project_id],
        name=rule_name,
        action="evaluator",
        enabled=True,  # a rule created without this is silently disabled
        sampling_rate=1.0,  # score every matching span — tune to a real sampling rate for production volume
        trigger_scope="production",
        filters=[SpanFilterWrite(field="name", operator="=", value="chat")],
        code=SpanUserDefinedMetricPythonCodeWrite(
            metric=SENSITIVE_DATA_METRIC_CODE,
            # Whole-section mapping — see the module docstring's GOTCHA note.
            arguments={"prompt_section": "input", "completion_section": "output"},
        ),
    )
    client.rest_client.automation_rule_evaluators.create_automation_rule_evaluator(request=rule)
    rule_id = find_existing_rule(client, project_id, rule_name).id
    print(f"Created span-level rule {rule_name!r} ({rule_id}), filtered to span name = 'chat'.")
    return rule_id


async def main():
    print("=" * 78)
    print("CONTENT CAPTURE IS TURNING ON FOR THE FIRST TIME IN THIS PACKET.")
    print("=" * 78)
    print(
        "Every session below runs with capture_content=True. Steps 01/02 ran every\n"
        "session with it OFF. This is a real, all-or-nothing tradeoff, not a default\n"
        "flip: real Copilot's enterprise-managed capture toggle is one switch for\n"
        "every prompt/completion/tool-argument org-wide, with no per-field granular\n"
        "control. Turning it on to DETECT sensitive data means first ACCEPTING that\n"
        "same content flows into the telemetry pipeline. This step demonstrates a\n"
        "CAPABILITY for discussion with your organization's governance/security\n"
        "stakeholder — it is NOT a recommendation to enable this in production. See\n"
        "this script's module docstring and the README for the full framing.\n"
    )

    client = opik.Opik()

    print("=" * 78)
    print("SERVER-SIDE DETECTION — deploying the Opik online-evaluation rule FIRST")
    print("=" * 78)
    print(
        "The rule is created before any session below runs, so it's already live and able to "
        "score every 'chat' span these sessions produce — online scoring itself is asynchronous "
        "(allow up to ~1 minute after each run), but it does not depend on running this script "
        "twice.\n"
    )

    project_id = get_project_id(client, OPIK_PROJECT_NAME)
    rule_id = ensure_sensitive_data_rule(client, project_id)
    print(f"Rule ready: {rule_id}\n")

    sessions = []
    for ticket_id, developer, is_injected in SESSIONS:
        ticket = _TICKETS_BY_ID[ticket_id]
        result = await run_copilot_session(
            ticket_id=ticket_id,
            developer=developer,
            team=ticket["team"],
            repository=ticket["repository"],
            steps=None,  # full /specify -> /plan -> /tasks -> /implement sequence
            capture_content=True,
        )
        sessions.append({"ticket_id": ticket_id, "thread_id": result["thread_id"], "is_injected": is_injected})
        tag = "[INJECTED RISK SCENARIO]" if is_injected else "[normal — false-positive check]"
        print(f"[OK] {ticket_id} {tag} thread={result['thread_id']} steps={result['steps_run']}")

    flush()
    print(f"\nLogged {len(SESSIONS)} sessions with capture_content=True. Querying back captured content ...\n")

    print("=" * 78)
    print("CLIENT-SIDE DETECTION — risk_patterns.scan_for_sensitive_data() over real captured content")
    print("=" * 78)

    any_normal_false_positive = False
    for sess in sessions:
        traces = client.search_traces(
            project_name=OPIK_PROJECT_NAME,
            filter_string=f'thread_id = "{sess["thread_id"]}"',
            wait_for_at_least=1,
        )
        session_findings = []
        for t in traces:
            spans = client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=t.id, wait_for_at_least=1)
            for s in spans:
                if s.name not in _CONTENT_SPAN_NAMES:
                    continue
                text = _captured_text(s)
                hits = scan_for_sensitive_data(text)
                for hit in hits:
                    session_findings.append((t.name, s.name, s.id, hit["category"], hit["match"]))

        tag = "[INJECTED RISK SCENARIO]" if sess["is_injected"] else "[normal]"
        print(f"\n{sess['ticket_id']} {tag} (thread={sess['thread_id']}): {len(session_findings)} finding(s)")
        for trace_name, span_name, span_id, category, match in session_findings:
            print(f"    trace={trace_name:12s} span={span_name:12s} {span_id}  category={category:26s} match={match!r}")

        if sess["is_injected"] and not session_findings:
            print("    *** EXPECTED a hit here (deliberately-injected risk scenario) but found none! ***")
        if not sess["is_injected"] and session_findings:
            any_normal_false_positive = True
            print(
                "    *** Unexpected hit on a NORMAL session — false positive. Inspect the match above; "
                "generated markdown occasionally contains an incidental email-shaped or digit-run string. ***"
            )

    if not any_normal_false_positive:
        print(
            "\nNo false positives across the 3 normal sessions — only the deliberately-injected "
            "SEC-201 scenario flagged a hit, as expected."
        )

    print("\n" + "=" * 78)
    print("SERVER-SIDE DETECTION — checking the online rule actually scored these sessions")
    print("=" * 78)
    print(
        "\nOnline scoring is asynchronous (allow up to ~1 minute) — waiting briefly, then checking "
        "every 'chat' span from the sessions just run above for a 'sensitive_data_detected' score.\n"
    )
    time.sleep(20)

    any_missing_score = False
    for sess in sessions:
        traces = client.search_traces(
            project_name=OPIK_PROJECT_NAME,
            filter_string=f'thread_id = "{sess["thread_id"]}"',
        )
        scored = []
        for t in traces:
            for s in client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=t.id):
                if s.name == "chat" and s.feedback_scores:
                    match = next((fs for fs in s.feedback_scores if fs.name == "sensitive_data_detected"), None)
                    if match:
                        scored.append(match.value)
        tag = "[INJECTED RISK SCENARIO]" if sess["is_injected"] else "[normal]"
        if scored:
            print(f"{sess['ticket_id']} {tag}: sensitive_data_detected = {scored}")
        else:
            any_missing_score = True
            print(f"{sess['ticket_id']} {tag}: no score yet — scoring may still be in flight, check again shortly")

    if any_missing_score:
        print(
            "\nIf a score is still missing after a minute or two, debug with: "
            f"client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id={rule_id!r})"
        )
    print("\nSee 03_risk_governance.md for the UI checklist.")


if __name__ == "__main__":
    asyncio.run(main())

# sensitive-data-in-prompt is ONE worked risk category, picked because it maps
# directly onto a real, currently-off toggle (capture_content) and a concrete,
# explainable regex-based detector (risk_patterns.py). The full risk taxonomy
# a customer's governance/security team actually cares about (broader PII
# categories, internal secret-format conventions, license/compliance
# language, whatever else governance flags) needs a working session with
# that team to define — this script does not attempt to guess the rest of it.
