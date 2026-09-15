"""
Step 01 — Session Tracing

Runs ~12 synthetic Spec-Kit sessions through copilot_session.py — a mix of
developers, teams, repositories, and workflows (some sessions run the full
/specify -> /plan -> /tasks -> /implement sequence, some stop early, one
revisits /implement twice to model a human iterating on a failed attempt).
Every session runs with `capture_content=False` — this step is pure
adoption/usage tracking, no content capture needed yet (Step 03 turns it on).

Each session opens one Opik thread (`gen_ai.conversation.id`); each turn
within it is one Opik trace, reconstructed purely server-side from a
hand-built OTel span tree sent over raw OTLP (see copilot_session.py).

After logging, this script queries back via `opik.Opik().search_traces(...)`
and prints breakdowns by repository / team / workflow-step. Repository is
queried directly; team is repository joined against `repo_team_map.py`;
workflow-step is only a coarse implement/other heuristic. A fourth
breakdown, developer, is not queryable from Opik at all — see the printed
callout below and the README for why.

Docs: https://www.comet.com/docs/opik/v1/tracing/log_traces/

Usage:
    python 01_session_tracing/01_session_tracing.py
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import opik

from copilot_session import flush, run_copilot_session, OPIK_PROJECT_NAME
from repo_team_map import get_team
from spec_kit_artifacts import DEVELOPERS, TICKETS

# (ticket_id, developer, steps) — steps=None means the full 4-step sequence.
# `developer` here is HARNESS bookkeeping only (see the callout this script
# prints below) — it is never sent to Opik/Copilot telemetry in any form.
# Deliberately varied: full sessions, sessions that stop early (only
# /specify, or /specify+/plan), and one that revisits /implement twice
# (a human iterating after a first attempt) — this is what this step's
# adoption/workflow-usage breakdown is checking Opik can answer.
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

# Structural signal for the workflow-step heuristic: a turn is classified
# "implement" only if its invoke_agent span tree contains one of these
# execute_tool calls. specify/plan/tasks are NOT distinguishable from each
# other via structure alone — see the printed callout below.
_IMPLEMENT_TOOL_NAMES = {"applyPatch", "runTests"}


def _repository_of(trace) -> str:
    """github.copilot.git.repository — empirically confirmed to land on
    trace.input (the root invoke_agent span's default attribute bucket;
    nothing about it matches a GenAI/General OTel mapping rule), NOT
    trace.metadata. See README for the full mapping-rule write-up."""
    return (trace.input or {}).get("github.copilot.git.repository", "unknown")


def _is_implement_trace(client: opik.Opik, trace_id: str) -> bool:
    spans = client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=trace_id, wait_for_at_least=1)
    for s in spans:
        if s.name != "execute_tool":
            continue
        tool_name = (s.metadata or {}).get("name")  # gen_ai.tool.name -> metadata["name"]
        if tool_name in _IMPLEMENT_TOOL_NAMES:
            return True
    return False


async def main():
    thread_ids = []
    expected_trace_count = 0
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
        thread_ids.append(result["thread_id"])
        expected_trace_count += len(result["steps_run"])
        print(
            f"[OK] {ticket_id} dev={developer} steps={result['steps_run']} "
            f"tokens_in={result['input_tokens']} tokens_out={result['output_tokens']} "
            f"thread={result['thread_id']}"
        )

    flush()
    print(
        f"\nLogged {len(SESSIONS)} sessions ({expected_trace_count} turns/traces total). "
        "Querying back via search_traces() ..."
    )

    client = opik.Opik()
    traces = client.search_traces(
        project_name=OPIK_PROJECT_NAME,
        max_results=500,
        wait_for_at_least=expected_trace_count,
    )
    # Only look at traces from the sessions just run (in case the project has older data).
    traces = [t for t in traces if t.thread_id in set(thread_ids)]
    traces_by_thread = {tid: [t for t in traces if t.thread_id == tid] for tid in thread_ids}

    def _print_breakdown(title, counter):
        print(f"{title}:")
        for key, count in counter.most_common():
            print(f"  {key:30s} {count:3d} turns")
        print()

    # --- 1. Repository breakdown — REAL, queried straight from Opik -------
    by_repo = Counter(_repository_of(t) for t in traces)
    print("=== Repository breakdown (real — from trace.input, queried from Opik) ===")
    _print_breakdown("Turns by repository", by_repo)

    # --- 2. Team breakdown — REAL repository join against harness-side map -
    # `team` is NOT a Copilot/Opik attribute (see repo_team_map.py). This is
    # an explicit external join: repository (real, from Opik) -> team (a
    # plain dict standing in for the customer's own CODEOWNERS/org chart).
    by_team = Counter(get_team(_repository_of(t)) for t in traces)
    print("=== Team breakdown (repository queried from Opik, JOINED against repo_team_map.py — NOT an Opik field) ===")
    _print_breakdown("Turns by team", by_team)

    # --- 3. Developer breakdown — NOT QUERYABLE FROM OPIK. Say so loudly. --
    print("=" * 78)
    print("DEVELOPER BREAKDOWN: NOT AVAILABLE FROM OPIK OR REAL COPILOT TELEMETRY.")
    print("=" * 78)
    print(
        "Real GitHub Copilot Chat's OTel export carries no attribute that identifies\n"
        "the developer driving a turn, anywhere in its documented schema. The one\n"
        "theoretical lever — an org injecting developer identity via OTel resource-\n"
        "level attributes — doesn't work either: Opik's ingestion pipeline only reads\n"
        "span-level attributes. There is no real path to a per-developer breakdown\n"
        "from Opik today. See the README for the full write-up.\n"
    )
    print(
        "Purely for demo narrative, here is what the HARNESS itself happens to know\n"
        "(because we generated these synthetic sessions) — this is NOT derived from\n"
        "Opik in any way and a real customer could NOT reproduce this breakdown:"
    )
    harness_by_developer = Counter()
    for ticket_id, developer, steps in SESSIONS:
        harness_by_developer[developer] += len(steps or ["specify", "plan", "tasks", "implement"])
    _print_breakdown("  [HARNESS-ONLY, not from Opik] Turns by developer", harness_by_developer)

    # --- 4. Workflow-step breakdown — PARTIAL gap, coarse heuristic only ---
    print("=" * 78)
    print("WORKFLOW-STEP BREAKDOWN: PARTIAL GAP — only a coarse implement/other split.")
    print("=" * 78)
    print(
        "No real Copilot attribute identifies which Spec-Kit slash command a turn\n"
        "represents. The only structural (non-content) signal available: a turn is\n"
        "classified 'implement' if its span tree contains an applyPatch/runTests\n"
        "execute_tool call. /specify vs /plan vs /tasks are NOT distinguishable from\n"
        "each other via structure alone — that would require capture_content=True\n"
        "to inspect actual prompt text (a later step in this packet).\n"
    )
    implement_count = 0
    other_count = 0
    print("Per-session turn classification (thread_id: N turns, of which M classified 'implement'):")
    for thread_id, thread_traces in traces_by_thread.items():
        n_implement = sum(1 for t in thread_traces if _is_implement_trace(client, t.id))
        n_other = len(thread_traces) - n_implement
        implement_count += n_implement
        other_count += n_other
        print(
            f"  {thread_id:30s} {len(thread_traces):2d} turns  "
            f"({n_implement} implement, {n_other} other/unclassifiable)"
        )
    print(f"\nTotals: {implement_count} implement-classified turns, {other_count} other (specify/plan/tasks, indistinguishable).\n")

    print(f"Total traces found: {len(traces)} across {len(thread_ids)} sessions.")
    print("Done. See 01_session_tracing.md for the UI checklist.")


if __name__ == "__main__":
    asyncio.run(main())
