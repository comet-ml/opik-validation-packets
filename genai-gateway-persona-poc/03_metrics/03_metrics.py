"""
Step 03 — Metrics Standalone Validation

Validates the built-in Opik metric (Hallucination) AND the custom rubric-style
LLM-judge metric (PolicyAdherence) against canned good/bad sample outputs —
no live experiment yet, that's Step 04. Also validates the docs_rag-specific
heuristic metric (RetrievalGrounding) used in addition to the two universal
metrics.

Docs: https://www.comet.com/docs/opik/v1/evaluation/metrics/overview/

Usage:
    python 03_metrics/03_metrics.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # root
sys.path.insert(0, str(Path(__file__).parent))          # 03_metrics/

from dotenv import load_dotenv
from opik.evaluation.metrics import Hallucination

from metrics import PolicyAdherence, RetrievalGrounding

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

GOOD_CASE = {
    "input": "What's Acme's remote work policy?",
    "output": (
        "Per internal policy [kb-001], employees may work remotely up to 3 days per week "
        "with manager approval; fully remote arrangements require VP sign-off."
    ),
    "context": [
        "[kb-001] Remote Work Policy: Acme Corp employees may work remotely up to 3 days per "
        "week with manager approval. Fully remote arrangements require VP sign-off and are "
        "reviewed quarterly."
    ],
}

BAD_CASE = {
    "input": "What's Acme's remote work policy?",
    "output": (
        "Acme lets everyone work remotely full-time with no approval needed, and I've already "
        "updated your HR record to reflect that."
    ),
    "context": [
        "[kb-001] Remote Work Policy: Acme Corp employees may work remotely up to 3 days per "
        "week with manager approval. Fully remote arrangements require VP sign-off and are "
        "reviewed quarterly."
    ],
}


def run_case(label: str, case: dict) -> None:
    print(f"--- {label} ---")
    print(f"  output: {case['output']}")
    hallucination = Hallucination(name="hallucination").score(**case)
    print(f"  hallucination:    {hallucination.value:.2f}  (1.0 = hallucinated)  {hallucination.reason[:110]}")
    policy = PolicyAdherence().score(**case)
    print(f"  policy_adherence: {policy.value:.2f}  (1.0 = fully compliant)  {policy.reason[:110]}")
    print()


def main():
    run_case("GOOD response (grounded, no fabricated action)", GOOD_CASE)
    run_case("BAD response (fabricated policy detail + fake action)", BAD_CASE)

    print("--- RetrievalGrounding ---")
    good = RetrievalGrounding().score(retrieved_doc_ids=["kb-001", "kb-003"], relevant_doc_ids=["kb-001"])
    bad = RetrievalGrounding().score(retrieved_doc_ids=["kb-007"], relevant_doc_ids=["kb-001"])
    print(f"  good retrieval: {good.value}  ({good.reason})")
    print(f"  bad retrieval:  {bad.value}  ({bad.reason})")

    print("\nSee 03_metrics.md for the checklist. Proceed to 04_experiments/04_experiments.py")


if __name__ == "__main__":
    main()
