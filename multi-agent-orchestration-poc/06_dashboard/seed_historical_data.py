"""
Step 06a — Seed Backdated Online-Eval History

Seeds ~12 backdated "orchestrator_run" data points spread over the past 14
days, with a deliberate quality dip (around day ~8) and a recovery by the
most recent days — the kind of trend Step 02's `orchestration_correctness`
AND `rag_groundedness` online evaluation rules would produce over several
weeks of real traffic. Tagged "anomaly" (alongside the online-eval-summary
tag) so they match the real rag-groundedness rule's trace filter, same as a
real anomaly-routed trace would.

Uses Opik/utils/historical_logger.py's `log_trace()` for backdated
trace/span ID generation (so points sort correctly on the Opik timeline).
The dip-then-recovery shape itself is custom (a Gaussian bump/dip centered
partway through the window) — historical_logger's own `log_metric_arc()` /
`apply_structural_arc()` only support a monotonic one-way degrade, not a
dip-and-recover, so this script applies feedback scores and per-span
cost/duration directly instead of going through those two helpers.

NOTE: some Opik Cloud workspace tiers enforce a 24h "ingestion window" on
backdated trace IDs — if this fails with `reason 'too_old'`, your workspace
doesn't allow backdating this far; lower DAYS_BACK until it succeeds, or
check with Comet about your plan's historical-ingestion window.

Usage:
    python 06_dashboard/seed_historical_data.py
"""
import datetime
import math
import os
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))                  # root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))    # Opik/ (for utils.*)

from dotenv import load_dotenv
import opik

from utils.historical_logger import log_trace

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")
ORCHESTRATION_FRAMEWORK = "microsoft_agent_framework"

N_POINTS = 12
DAYS_BACK = 14
RNG = random.Random(42)

TAG = "online-eval-summary"


def _dip(position: float, baseline: float, trough: float, center: float = 0.55, width: float = 0.22) -> float:
    """Gaussian dip below `baseline`, reaching (close to) `trough` at `center`."""
    factor = math.exp(-(((position - center) / width) ** 2))
    return baseline - (baseline - trough) * factor


def _bump(position: float, baseline: float, peak: float, center: float = 0.55, width: float = 0.22) -> float:
    """Gaussian bump above `baseline`, reaching (close to) `peak` at `center`."""
    factor = math.exp(-(((position - center) / width) ** 2))
    return baseline + (peak - baseline) * factor


def main():
    client = opik.Opik()

    now = datetime.datetime.now(datetime.timezone.utc)
    trace_positions = []  # (trace_id, position)

    for i in range(N_POINTS):
        position = i / (N_POINTS - 1)

        days_ago = DAYS_BACK * (1 - position)
        trace_start = (now - datetime.timedelta(days=days_ago)).replace(
            hour=RNG.randint(1, 5), minute=RNG.randint(0, 59), second=0, microsecond=0,
        )
        duration_s = _bump(position, baseline=1.5, peak=4.2)  # latency arc
        trace_end = trace_start + datetime.timedelta(seconds=duration_s)

        cost = _bump(position, baseline=0.0003, peak=0.0009)  # cost arc
        prompt_tokens = int(_bump(position, baseline=220, peak=480))
        completion_tokens = int(_bump(position, baseline=50, peak=130))

        span_id = str(uuid.uuid4())
        trace_dict = {
            "id": str(uuid.uuid4()),
            "name": "orchestrator_run",
            "start_time": trace_start,
            "end_time": trace_end,
            "input": {"query": "(historical simulated query)"},
            "output": {"summary": f"Orchestrator run (day -{int(days_ago)})"},
            "metadata": {"day_index": i, "orchestration_framework": ORCHESTRATION_FRAMEWORK},
            "tags": [TAG, "anomaly"],
        }
        span_dict = {
            "id": span_id,
            "name": "chat gpt-4o-mini",
            "type": "llm",
            "start_time": trace_start,
            "end_time": trace_end,
            "model": "gpt-4o-mini",
            "provider": "openai",
            "total_cost": round(cost, 6),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

        trace_id = log_trace(
            client, trace_dict, [span_dict],
            project_name=OPIK_PROJECT_NAME,
            randomize_scores=False,
        )
        trace_positions.append((trace_id, position))

    client.flush()
    print(f"Logged {N_POINTS} backdated orchestrator_run traces over the past {DAYS_BACK} days.")

    # Quality arcs: both online-eval scores dip down then recover — same
    # Gaussian center (rag_groundedness troughs slightly lower/later, so the
    # two lines are visually distinguishable), applied as trace-level
    # feedback scores after the traces are flushed (mirrors log_metric_arc's
    # own post-logging pattern), standing in for what Step 02's two rules
    # would have scored these traces as had they been running the whole
    # window.
    batch = []
    for trace_id, position in trace_positions:
        correctness = round(min(max(_dip(position, baseline=0.93, trough=0.5) + RNG.uniform(-0.03, 0.03), 0.0), 1.0), 3)
        groundedness = round(min(max(_dip(position, baseline=0.95, trough=0.4, center=0.6) + RNG.uniform(-0.03, 0.03), 0.0), 1.0), 3)
        batch.append({"id": trace_id, "name": "orchestration_correctness", "value": correctness})
        batch.append({"id": trace_id, "name": "rag_groundedness", "value": groundedness})

    client.log_traces_feedback_scores(batch, project_name=OPIK_PROJECT_NAME)
    client.flush()
    print(f"Logged orchestration_correctness + rag_groundedness dip-and-recovery arcs across {len(trace_positions)} traces.")
    print("\nProceed to 06_dashboard.py to build the dashboard.")


if __name__ == "__main__":
    main()
