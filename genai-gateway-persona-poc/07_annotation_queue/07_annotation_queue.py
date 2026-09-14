"""
Step 07 — Annotation Queue

Routes the flagged/regressed items from Step 06's `docs_rag-regression-check`
experiment into an Opik traces annotation queue, tagged with a
feedback-definition taxonomy (categorical `root_cause`, numeric `severity`)
for human triage.

An item is "flagged" if any of its scores crossed a simple quality threshold:

    hallucination        >= 0.3
    policy_adherence     <= 0.7
    retrieval_grounding  <  1.0

Reference pattern: field-service-csr-agent/scripts/add_to_annotation_queue.py

Docs: https://www.comet.com/docs/opik/v1/production/annotation_queues/

Usage:
    python 07_annotation_queue/07_annotation_queue.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import opik

from qa_taxonomy import ensure_taxonomy

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")
EXPERIMENT_NAME = "docs_rag-regression-check"

FLAG_THRESHOLDS = {
    "hallucination": lambda v: v >= 0.3,
    "policy_adherence": lambda v: v <= 0.7,
    "retrieval_grounding": lambda v: v < 1.0,
}


def find_flagged_trace_ids(client: opik.Opik, experiment_name: str) -> set:
    matches = [e for e in client.get_experiments_by_name(experiment_name) if e.name == experiment_name]
    if not matches:
        print(f"  (no experiment named {experiment_name!r} found — skipping; run 06_regression first)")
        return set()

    flagged = set()
    for item in matches[0].get_items():
        for score in (item.feedback_scores or []):
            check = FLAG_THRESHOLDS.get(score["name"])
            if check and score["value"] is not None and check(score["value"]):
                flagged.add(item.trace_id)
                break
    return flagged


def main():
    client = opik.Opik()

    queue = ensure_taxonomy(client, OPIK_PROJECT_NAME)
    print(f"Queue ready: {queue.name!r} ({queue.items_count} item(s) currently in queue).")

    flagged = find_flagged_trace_ids(client, EXPERIMENT_NAME)
    print(f"{len(flagged)} flagged trace(s) in {EXPERIMENT_NAME!r}.")

    if not flagged:
        print(
            "\nNo flagged traces found. This is expected if 06_regression.py's baseline "
            "comparison passed cleanly — run simulate_config_regression.py first to "
            "generate at least one real regression to route into the queue."
        )
        return

    traces = [client.get_trace_content(tid) for tid in flagged]
    queue.add_traces(traces)
    print(f"\nAdded {len(traces)} flagged trace(s) to {queue.name!r} "
          f"(queue now has {queue.items_count} item(s)).")
    print("See 07_annotation_queue.md for the UI checklist.")


if __name__ == "__main__":
    main()
