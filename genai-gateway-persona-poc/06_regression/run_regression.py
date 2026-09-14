"""
Step 06 — Regression Gate

Reruns the docs_rag golden set + metrics against the CURRENT app config and
statistically compares the result to the `docs_rag-baseline` experiment from
Step 04 (bootstrap CI + Welch t-test vs. baseline — same pattern as
elastic-poc's 06_statistical_metrics.py).

Use `--gate` to make this exit non-zero when a statistically significant
regression is detected (p < 0.05 AND the metric moved in the worse direction)
— see simulate_config_regression.py for a script that intentionally breaks the
docs_rag prompt so this gate demonstrably catches it, and schedule_example.py
for how to run this on a cadence.

Usage:
    python 06_regression/run_regression.py            # report only
    python 06_regression/run_regression.py --gate      # exit 1 on regression
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "03_metrics"))

import numpy as np
from scipy import stats

import opik
from opik.evaluation.metrics import Hallucination
from opik.evaluation.metrics.score_result import ScoreResult
from opik.evaluation.test_result import TestResult

from gateway import handle_request
from metrics import PolicyAdherence, RetrievalGrounding

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")
DATASET_NAME = "genai-gateway-docs-rag-qa"
BASELINE_NAME = "docs_rag-baseline"

METRICS = [Hallucination(name="hallucination"), PolicyAdherence(), RetrievalGrounding()]

# Direction each metric needs to move to count as a REGRESSION (not just a change).
# "higher_is_worse": e.g. hallucination — a positive delta vs. baseline is bad.
# "lower_is_worse":  everything else here — a negative delta vs. baseline is bad.
METRIC_DIRECTION = {
    "hallucination": "higher_is_worse",
    "policy_adherence": "lower_is_worse",
    "retrieval_grounding": "lower_is_worse",
}

SIGNIFICANCE_P = 0.05


def task_fn(dataset_item: dict) -> dict:
    result = handle_request(dataset_item["query"])
    return {
        "input": dataset_item["query"],
        "output": result["response"],
        "context": result["context"] or None,
        "tool_used": result["tool_used"],
        "retrieved_doc_ids": result["retrieved_doc_ids"],
        "relevant_doc_ids": dataset_item.get("relevant_doc_ids", []),
    }


def bootstrap_summary(results: list) -> list:
    """Mean + 95% bootstrap CI per metric, stored at the experiment level."""
    scores_by_name: dict = defaultdict(list)
    for result in results:
        for sr in result.score_results:
            if sr.value is not None:
                scores_by_name[sr.name].append(sr.value)

    output = []
    rng = np.random.default_rng(seed=42)
    for name, values in scores_by_name.items():
        arr = np.array(values)
        mean = float(arr.mean())
        boot_means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(1000)]
        ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
        output += [
            ScoreResult(name=f"{name}_mean", value=round(mean, 4)),
            ScoreResult(name=f"{name}_ci_low", value=round(float(ci_low), 4)),
            ScoreResult(name=f"{name}_ci_high", value=round(float(ci_high), 4)),
        ]
    return output


def make_compare_to_baseline(baseline_name: str):
    def compare_to_baseline(results: list) -> list:
        """Welch t-test vs. baseline_name: per-metric delta, p-value, significance, Cohen's d."""
        client = opik.Opik()
        matches = [e for e in client.get_experiments_by_name(baseline_name) if e.name == baseline_name]
        if not matches:
            raise ValueError(
                f"Baseline experiment {baseline_name!r} not found — run 04_experiments.py first."
            )
        baseline_scores: dict = defaultdict(list)
        for item in matches[0].get_items():
            for s in (item.feedback_scores or []):
                if s["value"] is not None:
                    baseline_scores[s["name"]].append(s["value"])

        current_scores: dict = defaultdict(list)
        for result in results:
            for sr in result.score_results:
                if sr.value is not None:
                    current_scores[sr.name].append(sr.value)

        output = []
        for name, current in current_scores.items():
            baseline = baseline_scores.get(name)
            if not baseline or len(current) < 2 or len(baseline) < 2:
                continue
            curr_arr, base_arr = np.array(current), np.array(baseline)
            delta = float(curr_arr.mean() - base_arr.mean())
            pooled_std = np.sqrt((curr_arr.std(ddof=1) ** 2 + base_arr.std(ddof=1) ** 2) / 2)

            if pooled_std == 0:
                # Both samples are constant (common here — several metrics score a
                # clean 0.0 or 1.0 on every item). Welch's t-test divides by the
                # pooled std and returns NaN in that case, which the backend
                # rejects as a JSON number — handle it explicitly instead: no
                # spread in either sample means "identical" (p=1.0) if the means
                # match, or a fully deterministic shift (p=0.0) if they don't.
                p_value = 1.0 if delta == 0 else 0.0
                effect_size = 0.0
            else:
                _, p_value = stats.ttest_ind(curr_arr, base_arr, equal_var=False)
                p_value = float(p_value)
                effect_size = delta / pooled_std

            output += [
                ScoreResult(name=f"{name}_delta", value=round(delta, 4)),
                ScoreResult(name=f"{name}_p_value", value=round(p_value, 4)),
                ScoreResult(name=f"{name}_significant", value=1.0 if p_value < SIGNIFICANCE_P else 0.0),
                ScoreResult(name=f"{name}_effect_size", value=round(float(effect_size), 4)),
            ]
        return output
    return compare_to_baseline


def find_regressions(experiment_scores: list) -> list:
    """Inspect `<metric>_significant` / `<metric>_delta` pairs and flag true regressions."""
    scores_by_name = {s.name: s.value for s in experiment_scores}
    regressions = []
    for metric_name, direction in METRIC_DIRECTION.items():
        sig_key, delta_key = f"{metric_name}_significant", f"{metric_name}_delta"
        if scores_by_name.get(sig_key) != 1.0:
            continue
        delta = scores_by_name.get(delta_key, 0.0)
        is_regression = (direction == "higher_is_worse" and delta > 0) or (
            direction == "lower_is_worse" and delta < 0
        )
        if is_regression:
            regressions.append((metric_name, delta, scores_by_name.get(f"{metric_name}_p_value")))
    return regressions


def run_check() -> list:
    """Run the docs_rag regression check against its Step 04 baseline."""
    client = opik.Opik()
    dataset = client.get_dataset(name=DATASET_NAME)

    print(f"\n── Regression check: docs_rag (vs. baseline={BASELINE_NAME!r}) ──")
    results = opik.evaluate(
        dataset=dataset,
        task=task_fn,
        scoring_metrics=METRICS,
        experiment_scoring_functions=[bootstrap_summary, make_compare_to_baseline(BASELINE_NAME)],
        experiment_name="docs_rag-regression-check",
        experiment_config={"baseline": BASELINE_NAME},
        project_name=OPIK_PROJECT_NAME,
        task_threads=4,
    )
    print(f"Done: {results.experiment_url}")

    regressions = find_regressions(results.experiment_scores)
    if regressions:
        print("  REGRESSION(S) DETECTED for docs_rag:")
        for name, delta, p in regressions:
            print(f"    - {name}: delta={delta:+.4f}  p={p}")
    else:
        print("  No statistically significant regression detected for docs_rag.")
    return regressions


def main():
    parser = argparse.ArgumentParser(description="Regression gate vs. Step 04 baseline.")
    parser.add_argument("--gate", action="store_true", help="Exit 1 if a regression is detected.")
    args = parser.parse_args()

    regressions = run_check()

    print("\nSee 06_regression.md for the UI checklist.")
    if args.gate and regressions:
        print(f"\nGATE FAILED — {len(regressions)} regression(s) detected.")
        sys.exit(1)


if __name__ == "__main__":
    main()
