"""
Step 02 — Human Oversight Tracking

Runs the same 12 synthetic Spec-Kit sessions as Step 01 (copied locally
rather than cross-imported), then queries back every turn's spans via
`opik.Opik().search_spans(...)` to identify and categorize human-oversight
signals — accept/reject, thumbs feedback, hook confirmations, and step
reruns — per session.

Since there's no `@opik.track` anywhere in this harness, this script can't
read a per-turn Opik trace ID back from `run_copilot_session`'s return value.
Instead, after flushing, it queries `search_traces(filter_string='thread_id
= "..."')` per session to get the real Opik-assigned trace IDs, then runs
`search_spans(trace_id=...)` against each one.

Four signal shapes, three of them real span attributes emitted
deterministically by copilot_session.py (seeded by `random.Random(thread_id)`,
so a given session always reproduces the same distribution), one derived
from the harness's own bookkeeping rather than a span:

    1. rejected_edit               — `github.copilot.edit.accepted == False`
                                      on the `applyPatch` `execute_tool` span.
    2. negative_feedback            — `github.copilot.feedback.vote == "down"`
                                      on a `chat` span.
    3. hook_confirmation_required   — `github.copilot.hook.decision == "ask"`
                                      on the `execute_hook` span whose
                                      `github.copilot.hook.name == "Stop"`.
    4. rerun                        — not a span attribute: a session's own
                                      `steps_run` list contains a step name
                                      more than once (e.g. AUTH-101's double
                                      `implement`) — a human re-triggering the
                                      same slash command after a first attempt.

None of these `github.copilot.*` attributes match a GenAI/General OTel
mapping rule on the backend, so they land in each span's `input` field, not
`metadata` — that's why this script reads them off `span.input`.

`team` is reconstructed the same honest way Step 01 does it: query
`github.copilot.git.repository` back from Opik and join it against
`repo_team_map.py` — not read off any Opik metadata field. `developer` can't
be reconstructed this way at all — see the callout this script prints,
consistent with Step 01.

============================================================================
ONLINE-EVALUATION RULE: edit_accepted (trace-level, real Opik rule)
============================================================================
On top of the client-side analysis above, this script also deploys a real
Opik online-evaluation rule that answers a narrower, always-on question as a
first-class feedback score on every future trace: "was every code edit in
this turn accepted, or was at least one rejected?"

Trace-level, not span-level: the raw signal lives on individual `applyPatch`
`execute_tool` spans, and a trace can in principle contain more than one (a
real multi-file `/implement` turn could issue several, each independently
accepted or rejected). The rule's Python code is written to handle N edits
per trace, not hardcoded to one. Filter: trace name = `invoke_agent` (every
trace in this packet), with the scoring logic handling non-implement turns
(no `applyPatch` span) gracefully.

The rule is self-contained Python, no local imports (the sandbox can't reach
this repo's own modules), and requests the trace's full span tree via the
reserved `arguments={"spans": "spans"}` key.

Scoring (metric name `edit_accepted`):
  * Zero applyPatch spans in the trace -> 1.0 ("no edits occurred in this
    turn" — vacuously true, not equivalent to a rejection).
  * At least one applyPatch span rejected -> 0.0.
  * All applyPatch spans accepted -> 1.0.

`enabled=True` is passed explicitly — a rule created without it is silently
disabled.

============================================================================
LIMITATION: a small fraction of `edit_accepted` scores can be wrong
============================================================================
Under OTLP batch ingestion, a trace's spans can still be writing to storage
at the exact moment this rule's scoring job fetches them, so the rule
occasionally reads an incomplete span list and scores "no edits occurred"
even when an edit (accepted or rejected) actually happened. In one test run
of 41 scored traces, about 10% were affected this way — including one case
where a genuine rejection was scored as accepted. There's no automatic
retry; a wrong score stays wrong until the trace is rescored manually. This
is a backend timing issue, not a bug in this rule's logic, and would affect
any trace-level rule that requests a trace's full span tree the same way.
Worth flagging as a product gap if a customer relies on this pattern.

Docs: https://www.comet.com/docs/opik/v1/production/online-evaluation/rules/

Usage:
    python 02_oversight_tracking/02_oversight_tracking.py
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import opik
from opik.rest_api.types.automation_rule_evaluator_write import (
    AutomationRuleEvaluatorWrite_UserDefinedMetricPython,
)
from opik.rest_api.types.trace_filter_write import TraceFilterWrite
from opik.rest_api.types.user_defined_metric_python_code_write import UserDefinedMetricPythonCodeWrite

from copilot_session import flush, run_copilot_session, OPIK_PROJECT_NAME
from repo_team_map import get_team
from spec_kit_artifacts import DEVELOPERS, TICKETS

# Identical (ticket_id, developer, steps) tuples as 01_session_tracing.py's
# SESSIONS — copied locally rather than cross-imported across numbered step
# folders, per this packet's convention. Same seeded rng per thread_id means
# the same oversight-signal distribution reproduces every run. `developer`
# is harness bookkeeping only (see the callout this script prints below) —
# it is never sent to Opik/Copilot telemetry in any form.
SESSIONS = [
    ("PROJ-101", DEVELOPERS[0], None),
    ("PROJ-114", DEVELOPERS[1], ["specify", "plan"]),
    ("PROJ-128", DEVELOPERS[0], None),
    ("INV-205", DEVELOPERS[2], None),
    ("INV-219", DEVELOPERS[3], ["specify"]),
    ("INV-233", DEVELOPERS[2], ["specify", "plan", "tasks"]),
    ("PORT-042", DEVELOPERS[4], None),
    ("PORT-057", DEVELOPERS[5], None),
    ("PORT-063", DEVELOPERS[4], ["specify", "plan"]),
    ("AUTH-088", DEVELOPERS[5], None),
    ("AUTH-101", DEVELOPERS[1], ["specify", "plan", "tasks", "implement", "implement"]),
    ("AUTH-115", DEVELOPERS[3], None),
]

_TICKETS_BY_ID = {t["ticket_id"]: t for t in TICKETS}


def _traces_for_thread(client: opik.Opik, thread_id: str):
    """Real Opik-assigned trace records for one session — there is no local
    trace_id to read back from run_copilot_session anymore (no Opik SDK call
    ever opens a trace), so this is the only way to find them."""
    return client.search_traces(
        project_name=OPIK_PROJECT_NAME,
        filter_string=f'thread_id = "{thread_id}"',
        wait_for_at_least=1,
    )


def _find_span_events(client: opik.Opik, trace_id: str) -> list:
    """Return [(driver, span_id), ...] of span-level oversight signals in one turn/trace."""
    events = []
    spans = client.search_spans(
        project_name=OPIK_PROJECT_NAME,
        trace_id=trace_id,
        wait_for_at_least=1,
    )
    for s in spans:
        span_input = s.input or {}

        if s.name == "execute_tool" and span_input.get("github.copilot.edit.accepted") is False:
            events.append(("rejected_edit", s.id))

        elif s.name == "chat" and span_input.get("github.copilot.feedback.vote") == "down":
            events.append(("negative_feedback", s.id))

        elif (
            s.name == "execute_hook"
            and span_input.get("github.copilot.hook.name") == "Stop"
            and span_input.get("github.copilot.hook.decision") == "ask"
        ):
            events.append(("hook_confirmation_required", s.id))

    return events


def _find_rerun_events(steps_run: list) -> list:
    """Return [("rerun", step_name), ...] — one per extra occurrence of a repeated step."""
    events = []
    for step, count in Counter(steps_run).items():
        for _ in range(count - 1):
            events.append(("rerun", step))
    return events


# ============================================================================
# Online rule — real, trace-scoped, user_defined_metric_python. See this
# file's module docstring for the full design rationale.
# ============================================================================
EDIT_ACCEPTED_METRIC_CODE = r'''
from opik.evaluation.metrics import BaseMetric
from opik.evaluation.metrics.score_result import ScoreResult


class EditAcceptedMetric(BaseMetric):
    def __init__(self, name: str = "edit_accepted"):
        super().__init__(name=name)

    def _flatten(self, spans):
        # Recursively walk the trace's full span tree — nested children live
        # under each span dict's own "spans" key.
        flat = []
        for s in spans or []:
            flat.append(s)
            flat.extend(self._flatten(s.get("spans")))
        return flat

    def score(self, spans=None, **kwargs):
        all_spans = self._flatten(spans)

        # Every applyPatch execute_tool span in this trace — a loop over ALL
        # matches (not just one), since a real multi-file /implement turn
        # could issue several, each independently accepted or rejected.
        # gen_ai.tool.name lands in the span's metadata under the key "name";
        # github.copilot.edit.accepted lands in the span's input.
        apply_patch_spans = [
            s for s in all_spans
            if (s.get("name") == "execute_tool"
                and (s.get("metadata") or {}).get("name") == "applyPatch")
        ]

        if not apply_patch_spans:
            # No edits happened in this turn (a specify/plan/tasks turn, or
            # an implement turn where nothing needed changing) — scored 1.0
            # as a vacuous truth, not treated as equivalent to a rejection.
            return ScoreResult(
                name="edit_accepted",
                value=1.0,
                reason="No edits occurred in this turn (no applyPatch span found) — scored 1.0 "
                       "vacuously (no edit to reject), not treated as equivalent to a rejection.",
            )

        total = len(apply_patch_spans)
        rejected = [
            s for s in apply_patch_spans
            if (s.get("input") or {}).get("github.copilot.edit.accepted") is False
        ]

        if rejected:
            return ScoreResult(
                name="edit_accepted",
                value=0.0,
                reason=f"{len(rejected)} of {total} edit(s) in this turn were rejected "
                       f"(github.copilot.edit.accepted == False).",
            )

        return ScoreResult(
            name="edit_accepted",
            value=1.0,
            reason=f"All {total} edit(s) in this turn were accepted (github.copilot.edit.accepted == True).",
        )
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


def ensure_edit_accepted_rule(client: opik.Opik, project_id: str) -> str:
    rule_name = "edit-accepted"
    existing = find_existing_rule(client, project_id, rule_name)
    if existing:
        print(f"Rule {rule_name!r} already exists ({existing.id}) — skipping creation.")
        return existing.id

    rule = AutomationRuleEvaluatorWrite_UserDefinedMetricPython(
        project_ids=[project_id],
        name=rule_name,
        action="evaluator",
        enabled=True,  # NOT the default — a rule created without this is silently disabled
        sampling_rate=1.0,  # score every matching trace — tune to a real sampling rate for production volume
        trigger_scope="production",
        filters=[TraceFilterWrite(field="name", operator="=", value="invoke_agent")],
        code=UserDefinedMetricPythonCodeWrite(
            metric=EDIT_ACCEPTED_METRIC_CODE,
            arguments={"spans": "spans"},  # reserved key — value is ignored, only the key matters
        ),
    )
    client.rest_client.automation_rule_evaluators.create_automation_rule_evaluator(request=rule)
    rule_id = find_existing_rule(client, project_id, rule_name).id
    print(f"Created trace-level rule {rule_name!r} ({rule_id}), filtered to trace name = 'invoke_agent'.")
    return rule_id


async def main():
    sessions = []
    for ticket_id, developer, steps in SESSIONS:
        ticket = _TICKETS_BY_ID[ticket_id]
        result = await run_copilot_session(
            ticket_id=ticket_id,
            developer=developer,
            team=ticket["team"],
            repository=ticket["repository"],
            steps=steps,
            capture_content=False,
        )
        sessions.append(
            {
                "ticket_id": ticket_id,
                "developer": developer,  # harness bookkeeping — see callout below
                "thread_id": result["thread_id"],
                "steps_run": result["steps_run"],
            }
        )
        print(
            f"[OK] {ticket_id} dev={developer} steps={result['steps_run']} "
            f"thread={result['thread_id']}"
        )

    flush()
    print(f"\nLogged {len(SESSIONS)} sessions. Querying back real trace IDs per session (by thread_id) ...")

    client = opik.Opik()

    print("=" * 78)
    print("DEVELOPER BREAKDOWN: NOT AVAILABLE FROM OPIK OR REAL COPILOT TELEMETRY.")
    print("=" * 78)
    print(
        "Session labels below show 'dev=...' for narrative convenience only — that\n"
        "value comes from this script's own SESSIONS list (harness bookkeeping), NOT\n"
        "from anything queried out of Opik. Real Copilot's OTel export carries no\n"
        "developer-identifying attribute anywhere, and the one theoretical lever\n"
        "(OTel resource-attribute injection) is a confirmed dead end — Opik's\n"
        "ingestion pipeline never reads resource-level attributes at all. See\n"
        "01_session_tracing.py's identical callout and the README for the full\n"
        "write-up.\n"
    )

    driver_counts = Counter()
    team_counts = Counter()
    session_rows = []  # (session_key, team, event_count, driver_counter)
    total_events = 0

    for sess in sessions:
        traces = _traces_for_thread(client, sess["thread_id"])
        trace_ids = [t.id for t in traces if t.id]

        # `team` reconstructed the honest way: repository queried back from
        # Opik (trace.input), joined against repo_team_map.py — NOT read off
        # any Opik metadata field, and deliberately NOT the harness's own
        # ticket["team"] value, to keep "what Opik can tell you" and "what we
        # happen to know" visibly separate (consistent with Step 01).
        repository = (traces[0].input or {}).get("github.copilot.git.repository", "unknown") if traces else "unknown"
        team = get_team(repository)

        session_events = []

        # Span-level signals: reject/negative-feedback/hook-confirmation,
        # queried back per turn (trace) in this session.
        for trace_id in trace_ids:
            session_events.extend(_find_span_events(client, trace_id))

        # Session-level signal: a rerun, derived from the harness's own
        # steps_run bookkeeping (not a span attribute at all).
        session_events.extend(_find_rerun_events(sess["steps_run"]))

        session_driver_counts = Counter(driver for driver, _ in session_events)
        session_key = f"{sess['ticket_id']} (dev={sess['developer']}, harness-only)"

        session_rows.append((session_key, team, len(session_events), session_driver_counts))
        driver_counts.update(session_driver_counts)
        team_counts[team] += len(session_events)
        total_events += len(session_events)

    print("\n=== Human Oversight Tracking — override/rerun events, per session ===\n")
    print(
        f"Total override/rerun events found across {len(SESSIONS)} sessions: {total_events} "
        "(each identifiable to its session/thread and, for span-level signals, its exact span)\n"
    )

    print("Breakdown by driver category (common drivers of human intervention):")
    if driver_counts:
        for driver, count in driver_counts.most_common():
            print(f"  {driver:28s} {count:3d} event(s)")
    else:
        print("  (none found)")
    print()

    print("Breakdown by session — override/rerun events identifiable per session (sorted, most first):")
    for session_key, team, count, drivers in sorted(session_rows, key=lambda r: -r[2]):
        driver_str = ", ".join(f"{d}={c}" for d, c in drivers.most_common()) or "none"
        print(f"  {session_key:38s} team={team:20s} {count:3d} event(s)  [{driver_str}]")
    print()

    print("Breakdown by team (real — repository from Opik trace.input, joined against repo_team_map.py):")
    for team, count in team_counts.most_common():
        print(f"  {team:24s} {count:3d} event(s)")
    print()

    print("=" * 78)
    print("SERVER-SIDE DETECTION — deploying a real Opik online-evaluation rule")
    print("=" * 78)
    print(
        "The breakdowns above answer 'frequency and drivers of human intervention' across the\n"
        "batch this script just ran. The rule below answers a narrower, always-on question — "
        "was every code edit in a given turn accepted, or was at least one rejected? — as a "
        "first-class 'edit_accepted' feedback score on every future trace, with zero per-run "
        "scripting required. See this file's module docstring for the full design rationale.\n"
    )

    project_id = get_project_id(client, OPIK_PROJECT_NAME)
    rule_id = ensure_edit_accepted_rule(client, project_id)

    print(
        "\nRule is live against every 'invoke_agent' trace (i.e. every turn) logged FROM NOW ON "
        "in this project — it does not retroactively score the sessions just run above (online "
        "scoring only evaluates traces as they arrive). Online scoring itself runs asynchronously "
        "(allow up to ~1 minute). Run this script again (or any new session) to see an "
        "'edit_accepted' feedback score land on each turn's trace."
    )
    print(
        "Debug if nothing shows up: "
        f"client.rest_client.automation_rule_evaluators.get_evaluator_logs_by_id(id={rule_id!r})"
    )
    print(
        "\nKNOWN LIMITATION (see this file's module docstring): a small fraction of scored traces "
        "can read an incomplete span list under OTLP batch ingestion and score 'no edits occurred' "
        "even when an edit happened — about 10% in one test run, including one real rejection scored "
        "as accepted. If a score for a known-implement turn looks wrong, cross-check with "
        "search_spans() before assuming a rule bug."
    )

    print("\nDone. See 02_oversight_tracking.md for the UI checklist. Proceed to 03_risk_governance/.")


if __name__ == "__main__":
    asyncio.run(main())
