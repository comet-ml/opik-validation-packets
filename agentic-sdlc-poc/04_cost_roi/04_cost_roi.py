"""
Step 04 — Cost & ROI Visibility

Validates per-repository/team cost breakdown and proposes an ROI metric.

============================================================================
SCOPE DECISION: this step covers the COST half of the criterion fully and
honestly. It does not attempt a full ROI metric. The optimization-signal
step — which would have correlated sessions against delivery outcomes
(merge time, revert rate, cycle time), the productivity/business-value
signal an ROI metric needs — was dropped from this build's scope (see
README "Not built yet"). Forcing a return-side number without that data
would mean fabricating it. Instead this script builds real cost visibility
and documents the ROI-metric half as a clearly-reasoned gap.
============================================================================

WHERE THE TOKEN NUMBERS COME FROM: `invoke_agent`'s own usage attributes are
set (matching the real documented Copilot schema) but never persist
server-side — Opik's backend nulls a span's usage whenever it's the direct
parent of a usage-bearing child, which `invoke_agent` always is here (its
`chat` child reports usage). `chat` spans are the one span type whose usage
reliably persists, so this script's `_chat_token_usage()` reads
`span.usage["prompt_tokens"]`/`["completion_tokens"]` off `chat` spans
directly. It also cross-checks that `trace.usage` (a separate, already-
populated rollup) agrees with summing the `chat` spans by hand — see
`_verify_usage_sources()`.

WHERE THE DOLLAR ESTIMATE COMES FROM: `GPT_4O_MINI_INPUT_USD_PER_1M_TOKENS`/
`..._OUTPUT_...` below are OpenAI's own published per-token rate for
`gpt-4o-mini` ($0.150 / 1M input tokens, $0.600 / 1M output tokens),
cross-checked against Opik's own internal price table. Opik does NOT
auto-populate `total_estimated_cost` on these spans today — its cost lookup
requires both a `model` and a `provider` attribute, and real Copilot's
documented schema never sends a provider attribute — which is why this
script computes the dollar math manually. This is an approximation of the
underlying OpenAI model cost, not a prediction of what GitHub would actually
bill — real Copilot billing can apply its own model-cost multiplier on top.
Treat these numbers as directionally useful for relative comparison, not a
substitute for GitHub's own billing statement.

DEVELOPER-LEVEL COST BREAKDOWN — same dead end as Steps 01-03: developer
identity has no real path into Opik or Copilot telemetry at all. This script
prints the same callout before showing a harness-only, clearly-labeled
per-developer view — the token counts are real, only the "developer"
grouping label is harness bookkeeping a real customer couldn't reproduce.

Docs: https://www.comet.com/docs/opik/v1/tracing/log_traces/

Usage:
    python 04_cost_roi/04_cost_roi.py
"""
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import opik

from copilot_session import flush, run_copilot_session, OPIK_PROJECT_NAME
from repo_team_map import get_team
from spec_kit_artifacts import DEVELOPERS, TICKETS

# OpenAI's published per-token rate for gpt-4o-mini (https://openai.com/api/pricing/):
# $0.150 / 1M input tokens, $0.600 / 1M output tokens — matches Opik's own internal
# LiteLLM-derived price table. See module docstring for why Opik doesn't auto-populate
# cost for us today and why this script computes it manually.
GPT_4O_MINI_INPUT_USD_PER_1M_TOKENS = 0.15
GPT_4O_MINI_OUTPUT_USD_PER_1M_TOKENS = 0.60

# (ticket_id, developer, steps) — steps=None means the full 4-step sequence. Reused tickets
# from spec_kit_artifacts.TICKETS, copied locally (not cross-imported) per this packet's
# convention — same shape as Steps 01/02/03's own local SESSIONS lists. Deliberately mixes
# full sessions, partial (early-stopped) sessions, and a rerun session across 4 different
# teams/repositories, so the cost breakdown below has real variation to show.
# `developer` is harness bookkeeping ONLY (see the callout this script prints) — it is never
# sent to Opik/Copilot telemetry in any form. capture_content=False: cost visibility only
# needs token counts, not prompt/completion text.
SESSIONS = [
    ("PROJ-101", DEVELOPERS[0], None),                                        # commerce-platform, full
    ("PROJ-114", DEVELOPERS[1], ["specify", "plan"]),                         # commerce-platform, partial
    ("INV-205", DEVELOPERS[2], None),                                         # supply-chain-eng, full
    ("INV-233", DEVELOPERS[2], ["specify", "plan", "tasks"]),                 # supply-chain-eng, partial
    ("PORT-042", DEVELOPERS[4], None),                                        # data-platform, full
    ("AUTH-088", DEVELOPERS[5], None),                                        # platform-security, full
    ("AUTH-101", DEVELOPERS[1], ["specify", "plan", "tasks", "implement", "implement"]),  # platform-security, rerun
]

_TICKETS_BY_ID = {t["ticket_id"]: t for t in TICKETS}


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000) * GPT_4O_MINI_INPUT_USD_PER_1M_TOKENS
        + (output_tokens / 1_000_000) * GPT_4O_MINI_OUTPUT_USD_PER_1M_TOKENS
    )


def _repository_of(trace) -> str:
    """github.copilot.git.repository lands on trace.input (root invoke_agent span's default
    attribute bucket — see README/Step 01), NOT trace.metadata."""
    return (trace.input or {}).get("github.copilot.git.repository", "unknown")


def _chat_token_usage(client: opik.Opik, trace_id: str) -> tuple:
    """Sum real gen_ai.usage.input_tokens/output_tokens off this trace's `chat` span(s) —
    the one span type where usage reliably persists (see module docstring).
    Returns (input_tokens, output_tokens)."""
    spans = client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=trace_id, wait_for_at_least=1)
    total_in = total_out = 0
    for s in spans:
        if s.name != "chat":
            continue
        usage = s.usage or {}
        total_in += usage.get("prompt_tokens", 0) or 0
        total_out += usage.get("completion_tokens", 0) or 0
    return total_in, total_out


def _check_native_cost_field(client: opik.Opik, trace_id: str) -> bool:
    """Live check (not assumed from source alone): does Opik auto-populate
    total_estimated_cost on this trace's chat span(s)? Returns True if any chat span in this
    trace already carries a non-zero total_estimated_cost (would mean this script's manual
    dollar math is redundant with something Opik already computed for us)."""
    spans = client.search_spans(project_name=OPIK_PROJECT_NAME, trace_id=trace_id, wait_for_at_least=1)
    for s in spans:
        if s.name == "chat" and (s.total_estimated_cost or 0) > 0:
            return True
    return False


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
    print(f"\nLogged {len(SESSIONS)} sessions. Querying back real per-turn token usage from `chat` spans ...")

    client = opik.Opik()

    # --- Per-session real token totals, queried back from chat spans -------
    # (thread_id -> {"repo", "team", "developer", "ticket_id", "input_tokens", "output_tokens"})
    session_totals = {}
    all_trace_ids_by_thread = {}

    for sess in sessions:
        traces = client.search_traces(
            project_name=OPIK_PROJECT_NAME,
            filter_string=f'thread_id = "{sess["thread_id"]}"',
            wait_for_at_least=1,
        )
        repository = _repository_of(traces[0]) if traces else "unknown"
        team = get_team(repository)

        session_in = session_out = 0
        trace_ids = []
        for t in traces:
            trace_ids.append(t.id)
            turn_in, turn_out = _chat_token_usage(client, t.id)
            session_in += turn_in
            session_out += turn_out

        all_trace_ids_by_thread[sess["thread_id"]] = trace_ids
        session_totals[sess["thread_id"]] = {
            "ticket_id": sess["ticket_id"],
            "developer": sess["developer"],
            "repository": repository,
            "team": team,
            "input_tokens": session_in,
            "output_tokens": session_out,
        }

    # --- Live verification: does trace.usage (a separate rollup) agree with --
    # --- summing this session's chat spans by hand? Don't assume — check. ---
    print("\n" + "=" * 78)
    print("LIVE VERIFICATION — chat-span usage (this script's source of truth) vs. trace.usage rollup")
    print("=" * 78)
    all_match = True
    checked = 0
    for thread_id, trace_ids in all_trace_ids_by_thread.items():
        for trace_id in trace_ids:
            t = client.search_traces(
                project_name=OPIK_PROJECT_NAME,
                filter_string=f'id = "{trace_id}"',
                wait_for_at_least=1,
            )[0]
            trace_usage = t.usage or {}
            trace_in = trace_usage.get("prompt_tokens", 0) or 0
            trace_out = trace_usage.get("completion_tokens", 0) or 0
            chat_in, chat_out = _chat_token_usage(client, trace_id)
            checked += 1
            if (trace_in, trace_out) != (chat_in, chat_out):
                all_match = False
                print(
                    f"  MISMATCH trace={trace_id}: chat-span sum=({chat_in},{chat_out}) "
                    f"vs trace.usage=({trace_in},{trace_out})"
                )
    if all_match:
        print(
            f"Confirmed across all {checked} traces just logged: trace.usage (a separate, already-populated "
            "rollup) exactly matches summing this trace's own `chat` span(s) by hand — because invoke_agent's "
            "usage is nulled before storage (see module docstring) and no other span type in this harness's "
            "shape carries usage. This script still reads from `chat` spans directly as its source of truth, "
            "not trace.usage, so this equivalence stays true even if that internal rollup mechanism changes."
        )

    # --- Live verification: Opik does NOT auto-populate total_estimated_cost -
    # --- for these spans (no `provider` attribute in real Copilot's schema). -
    any_native_cost = any(
        _check_native_cost_field(client, trace_id)
        for trace_ids in all_trace_ids_by_thread.values()
        for trace_id in trace_ids
    )
    print("\n" + "=" * 78)
    print("LIVE VERIFICATION — does Opik auto-populate total_estimated_cost on these chat spans?")
    print("=" * 78)
    if not any_native_cost:
        print(
            "Confirmed: no chat span across this run's traces carries a non-zero total_estimated_cost. "
            "Opik's cost lookup requires both a `model` and a `provider` attribute, and real Copilot's "
            "documented schema only ever sends `gen_ai.request.model`, never a provider attribute — so the "
            "lookup always misses. This is why this script computes the dollar estimate itself below, from "
            "the token counts queried above."
        )
    else:
        print(
            "UNEXPECTED: at least one chat span already carries a non-zero total_estimated_cost — Opik's "
            "own auto-cost pipeline is active for this project. Re-check whether a provider attribute is "
            "being set somewhere before trusting this script's manual estimate over that native field."
        )

    # --- Repository / team cost breakdown — REAL token counts + a manual $ --
    # --- estimate against a cited real per-token rate (see module docstring)-
    by_repo = defaultdict(lambda: {"turns": 0, "input_tokens": 0, "output_tokens": 0})
    by_team = defaultdict(lambda: {"turns": 0, "input_tokens": 0, "output_tokens": 0})

    for thread_id, trace_ids in all_trace_ids_by_thread.items():
        s = session_totals[thread_id]
        by_repo[s["repository"]]["turns"] += len(trace_ids)
        by_repo[s["repository"]]["input_tokens"] += s["input_tokens"]
        by_repo[s["repository"]]["output_tokens"] += s["output_tokens"]
        by_team[s["team"]]["turns"] += len(trace_ids)
        by_team[s["team"]]["input_tokens"] += s["input_tokens"]
        by_team[s["team"]]["output_tokens"] += s["output_tokens"]

    print("\n" + "=" * 78)
    print("COST BREAKDOWN BY REPOSITORY (real — repository from trace.input, tokens from chat spans)")
    print("=" * 78)
    total_in_all = total_out_all = 0
    for repo, agg in sorted(by_repo.items(), key=lambda kv: -estimate_cost_usd(kv[1]["input_tokens"], kv[1]["output_tokens"])):
        cost = estimate_cost_usd(agg["input_tokens"], agg["output_tokens"])
        total_in_all += agg["input_tokens"]
        total_out_all += agg["output_tokens"]
        print(
            f"  {repo:28s} {agg['turns']:3d} turns  "
            f"in={agg['input_tokens']:6d} out={agg['output_tokens']:6d}  "
            f"~${cost:.5f} (APPROXIMATE — see module docstring)"
        )

    print("\n" + "=" * 78)
    print("COST BREAKDOWN BY TEAM (repository queried from Opik, JOINED against repo_team_map.py — NOT an Opik field)")
    print("=" * 78)
    for team, agg in sorted(by_team.items(), key=lambda kv: -estimate_cost_usd(kv[1]["input_tokens"], kv[1]["output_tokens"])):
        cost = estimate_cost_usd(agg["input_tokens"], agg["output_tokens"])
        print(
            f"  {team:24s} {agg['turns']:3d} turns  "
            f"in={agg['input_tokens']:6d} out={agg['output_tokens']:6d}  "
            f"~${cost:.5f} (APPROXIMATE — see module docstring)"
        )

    total_cost_all = estimate_cost_usd(total_in_all, total_out_all)
    print(
        f"\nProject total across this run's {len(SESSIONS)} sessions: "
        f"in={total_in_all} out={total_out_all} tokens, ~${total_cost_all:.5f} estimated "
        f"(rate: ${GPT_4O_MINI_INPUT_USD_PER_1M_TOKENS}/1M input, ${GPT_4O_MINI_OUTPUT_USD_PER_1M_TOKENS}/1M "
        "output — gpt-4o-mini, OpenAI published rate, see module docstring for citation)."
    )

    # --- Developer-level cost breakdown — explicit dead end -----------------
    print("\n" + "=" * 78)
    print("DEVELOPER-LEVEL COST BREAKDOWN: NOT AVAILABLE FROM OPIK OR REAL COPILOT TELEMETRY.")
    print("=" * 78)
    print(
        "Same dead end as Steps 01/02/03: real GitHub Copilot Chat's OTel export carries no attribute\n"
        "that identifies the developer driving a turn, and there's no real path to a per-developer cost\n"
        "breakdown from Opik today — see the README for the full write-up.\n"
    )
    print(
        "Purely for demo narrative, here is a per-developer view using the harness's own bookkeeping for\n"
        "the 'developer' grouping label — the token counts themselves are real, only the grouping-by-\n"
        "developer attribution is not reproducible by a real customer from Opik or Copilot telemetry:"
    )
    by_developer = defaultdict(lambda: {"turns": 0, "input_tokens": 0, "output_tokens": 0})
    for thread_id, trace_ids in all_trace_ids_by_thread.items():
        s = session_totals[thread_id]
        by_developer[s["developer"]]["turns"] += len(trace_ids)
        by_developer[s["developer"]]["input_tokens"] += s["input_tokens"]
        by_developer[s["developer"]]["output_tokens"] += s["output_tokens"]
    for dev, agg in sorted(by_developer.items(), key=lambda kv: -estimate_cost_usd(kv[1]["input_tokens"], kv[1]["output_tokens"])):
        cost = estimate_cost_usd(agg["input_tokens"], agg["output_tokens"])
        print(
            f"  [HARNESS-ONLY grouping, tokens real] {dev:16s} {agg['turns']:3d} turns  "
            f"in={agg['input_tokens']:6d} out={agg['output_tokens']:6d}  ~${cost:.5f}"
        )

    # --- The ROI-metric gap — proposed shape, cost half calculated, return --
    # --- half explicitly out of scope. Not faked. --------------------------
    print("\n" + "=" * 78)
    print("ROI METRIC: SHAPE PROPOSED, COST HALF CALCULATED, RETURN-SIGNAL HALF OUT OF SCOPE.")
    print("=" * 78)
    print(
        "An ROI metric needs two things combined: a COST signal and a RETURN (productivity/business-value)\n"
        "signal. This step builds the cost half fully and honestly — real token counts queried from Opik's\n"
        "`chat` spans, rolled up by repository/team, converted to an approximate dollar figure against a\n"
        "cited real OpenAI per-token rate (see the breakdowns above).\n"
        "\n"
        "It does NOT calculate a full ROI number, because the return-signal half needs delivery-outcome\n"
        "data (PR merge time, revert rate, Jira cycle time) correlated against these sessions — exactly what\n"
        "the optimization-signal step would have built, and that step was explicitly dropped from this\n"
        "build's scope (see the README's 'Not built yet' section). Forcing a return-side number without that\n"
        "data source would mean fabricating it; this script does not do that.\n"
        "\n"
        "PROPOSED SHAPE (not calculated here):\n"
        "    roi_per_session = return_signal(session) / cost_usd(session)\n"
        "  where cost_usd(session) is exactly what this script computes above, and return_signal(session) is\n"
        "  a delivery-outcome or oversight-quality proxy for that session's ticket, once available.\n"
        "\n"
        "One plausible RETURN-signal candidate already built elsewhere in this packet: Step 02's\n"
        "`edit_accepted` online-evaluation rule (github.copilot.edit.accepted rolled up per trace) is a\n"
        "cheap, already-live proxy for 'did this turn's output need a human override.' Pairing\n"
        "1 - override_rate per session against this step's cost_usd(session) would be a reasonable first ROI\n"
        "proxy if/when this step is revisited — named here as the most promising next step, not implemented.\n"
        "\n"
        "This is the honest way to answer the test plan's 'at least one ROI metric proposed' clause: the\n"
        "SHAPE of one is proposed, its cost half is calculated for real, and what's missing to complete it is\n"
        "stated plainly rather than glossed over."
    )

    print("\nDone. See 04_cost_roi.md for the UI checklist.")


if __name__ == "__main__":
    asyncio.run(main())
