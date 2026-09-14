"""
Step 05 — Benchmarking

Re-runs the same evaluation loop from Step 04 for every model in MODEL_VARIANTS,
so results are directly comparable in the Opik UI on cost/latency/quality across
model variants.

2 experiments total (one per model variant), each named `docs_rag-<model>` so
they group naturally in the Opik experiments list.

Docs: https://www.comet.com/docs/opik/v1/evaluation/evaluate_your_llm/

Usage:
    python 05_benchmarking/05_benchmarking.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "03_metrics"))

import opik
from opik.evaluation.metrics import Hallucination

from gateway import handle_request
from metrics import PolicyAdherence, RetrievalGrounding

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")
ORCHESTRATION_FRAMEWORK = "custom"
DATASET_NAME = "genai-gateway-docs-rag-qa"
MODEL_VARIANTS = ["openai/gpt-4o-mini", "openai/gpt-4o"]  # TODO(SE): real models to compare

METRICS = [Hallucination(name="hallucination"), PolicyAdherence(), RetrievalGrounding()]


def make_task_fn(model: str):
    def task_fn(dataset_item: dict) -> dict:
        result = handle_request(dataset_item["query"], model=model)
        return {
            "input": dataset_item["query"],
            "output": result["response"],
            "context": result["context"] or None,
            "tool_used": result["tool_used"],
            "retrieved_doc_ids": result["retrieved_doc_ids"],
            "relevant_doc_ids": dataset_item.get("relevant_doc_ids", []),
        }
    return task_fn


def main():
    client = opik.Opik()

    dataset = client.get_dataset(name=DATASET_NAME)

    for model in MODEL_VARIANTS:
        model_short = model.split("/")[-1]
        experiment_name = f"docs_rag-{model_short}"
        print(f"\n── Running: {experiment_name} ──")

        results = opik.evaluate(
            dataset=dataset,
            task=make_task_fn(model),
            scoring_metrics=METRICS,
            experiment_name=experiment_name,
            experiment_config={
                "model": model,
                "orchestration_framework": ORCHESTRATION_FRAMEWORK,
            },
            project_name=OPIK_PROJECT_NAME,
            task_threads=4,
        )
        print(f"Done: {results.experiment_url}")

    print("\nSee 05_benchmarking.md for the UI checklist.")


if __name__ == "__main__":
    main()
