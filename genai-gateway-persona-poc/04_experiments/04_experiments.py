"""
Step 04 — Experiments

Runs one opik.evaluate() against the real AcmeChat app (gateway.handle_request)
over the docs_rag dataset, using the two universal metrics from Step 03
(Hallucination + PolicyAdherence) plus the docs_rag-specific RetrievalGrounding
metric.

Docs: https://www.comet.com/docs/opik/v1/evaluation/evaluate_your_llm/

Usage:
    python 04_experiments/04_experiments.py
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))            # root
sys.path.insert(0, str(Path(__file__).parent.parent / "03_metrics"))  # metrics

import opik
from opik.evaluation.metrics import Hallucination

from gateway import handle_request
from metrics import PolicyAdherence, RetrievalGrounding

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")
ORCHESTRATION_FRAMEWORK = "custom"
DATASET_NAME = "genai-gateway-docs-rag-qa"


def get_git_metadata() -> dict:
    def _run(cmd):
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return "unknown"
    return {
        "git_sha": _run(["git", "rev-parse", "--short=8", "HEAD"]),
        "git_branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    }


def task_fn(dataset_item: dict) -> dict:
    """Task function for opik.evaluate() — calls the real gateway."""
    result = handle_request(dataset_item["query"])
    return {
        "input": dataset_item["query"],
        "output": result["response"],
        "context": result["context"] or None,
        "tool_used": result["tool_used"],
        "retrieved_doc_ids": result["retrieved_doc_ids"],
        # Pass dataset ground truth straight through so the metric's
        # scoring_inputs (dataset_item merged with task_output) always has it,
        # even though opik.evaluate() already does this merge automatically.
        "relevant_doc_ids": dataset_item.get("relevant_doc_ids", []),
    }


METRICS = [Hallucination(name="hallucination"), PolicyAdherence(), RetrievalGrounding()]


def main():
    client = opik.Opik()
    git = get_git_metadata()

    dataset = client.get_dataset(name=DATASET_NAME)

    experiment_config = {
        **git,
        "orchestration_framework": ORCHESTRATION_FRAMEWORK,
        "dataset": DATASET_NAME,
    }
    print(f"\n── Running experiment: docs_rag-baseline (dataset={DATASET_NAME}) ──")

    results = opik.evaluate(
        dataset=dataset,
        task=task_fn,
        scoring_metrics=METRICS,
        experiment_name="docs_rag-baseline",
        experiment_config=experiment_config,
        project_name=OPIK_PROJECT_NAME,
        task_threads=4,
    )
    print(f"Done: {results.experiment_url}")

    print("\nSee 04_experiments.md for the UI checklist.")


if __name__ == "__main__":
    main()
