"""
Step 08a — Seed Backdated Regression-Summary History

Seeds ~12 backdated "nightly regression check" data points spread over the
past 14 days, with a deliberate quality dip (around day ~8) and a recovery by
the most recent days — the kind of trend a customer's regression gate
(Step 06) would produce if run on a schedule (see schedule_example.py) over
several weeks.

Uses Opik/utils/historical_logger.py's `log_trace()` for backdated trace/span
ID generation (so points sort correctly on the Opik timeline). The
dip-then-recovery shape itself is custom (a Gaussian bump/dip centered partway
through the window) — historical_logger's own `log_metric_arc()` /
`apply_structural_arc()` only support a monotonic one-way degrade, not a
dip-and-recover, so this script applies feedback scores and per-span
cost/duration directly instead of going through those two helpers.

NOTE: some Opik Cloud workspace tiers enforce a 24h "ingestion window" on
backdated trace IDs — if this fails with `reason 'too_old'`, your workspace
doesn't allow backdating this far; lower DAYS_BACK until it succeeds, or
check with Comet about your plan's historical-ingestion window.

Usage:
    python 08_dashboard/seed_historical_data.py
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

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")
ORCHESTRATION_FRAMEWORK = "custom"

N_POINTS = 12
DAYS_BACK = 14
RNG = random.Random(42)

TAG = "regression-summary"


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
        duration_s = _bump(position, baseline=1.8, peak=5.5)  # latency arc
        trace_end = trace_start + datetime.timedelta(seconds=duration_s)

        cost = _bump(position, baseline=0.00035, peak=0.0012)  # cost arc
        prompt_tokens = int(_bump(position, baseline=180, peak=420))
        completion_tokens = int(_bump(position, baseline=40, peak=110))

        span_id = str(uuid.uuid4())
        trace_dict = {
            "id": str(uuid.uuid4()),
            "name": "regression_summary",
            "start_time": trace_start,
            "end_time": trace_end,
            "input": {"check": "nightly-regression-gate"},
            "output": {"summary": f"Nightly regression check for docs_rag (day -{int(days_ago)})"},
            "metadata": {"day_index": i, "orchestration_framework": ORCHESTRATION_FRAMEWORK},
            "tags": [TAG],
        }
        span_dict = {
            "id": span_id,
            "name": "regression_check_llm",
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
    print(f"Logged {N_POINTS} backdated regression-summary traces over the past {DAYS_BACK} days.")

    # Quality arc: policy_adherence dips down, hallucination dips up — same
    # Gaussian center, applied as trace-level feedback scores after the
    # traces are flushed (mirrors log_metric_arc's own post-logging pattern).
    batch = []
    for trace_id, position in trace_positions:
        policy_adherence = round(min(max(_dip(position, baseline=0.94, trough=0.55) + RNG.uniform(-0.03, 0.03), 0.0), 1.0), 3)
        hallucination = round(min(max(_bump(position, baseline=0.03, peak=0.50) + RNG.uniform(-0.03, 0.03), 0.0), 1.0), 3)
        batch.append({"id": trace_id, "name": "policy_adherence", "value": policy_adherence})
        batch.append({"id": trace_id, "name": "hallucination", "value": hallucination})

    client.log_traces_feedback_scores(batch, project_name=OPIK_PROJECT_NAME)
    client.flush()
    print(f"Logged quality arc (policy_adherence dip + hallucination bump, centered mid-window) "
          f"across {len(trace_positions)} traces.")
    print("\nProceed to 08_dashboard.py to build the dashboard.")


if __name__ == "__main__":
    main()
