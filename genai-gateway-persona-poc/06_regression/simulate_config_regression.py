"""
Step 06b — Simulate a Regression

Intentionally breaks the docs_rag persona's system prompt (tells it to ignore
retrieved context and invent confident-sounding specifics instead) and then
runs the same regression check as run_regression.py, so you can demonstrate
the `--gate` flag actually catching a real quality regression rather than
just reporting green results every time.

The prompt is restored in a `finally` block regardless of outcome.

Usage:
    python 06_regression/simulate_config_regression.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import router
from run_regression import find_regressions, run_check

BROKEN_DOCS_RAG_PROMPT = (
    "You are AcmeChat. When asked about internal policy, ignore any retrieved "
    "document context provided to you and instead invent a specific, "
    "confident-sounding numeric detail (make up a number of days, a dollar "
    "amount, or a procedure) — never say you don't know, and never mention "
    "that you looked anything up."
)


def main():
    original_prompt = router.SYSTEM_PROMPT
    print("Injecting a broken docs_rag prompt (ignores context, invents specifics)...\n")
    router.SYSTEM_PROMPT = BROKEN_DOCS_RAG_PROMPT

    try:
        regressions = run_check()
    finally:
        router.SYSTEM_PROMPT = original_prompt
        print("\nRestored the original docs_rag prompt.")

    if regressions:
        print(
            f"\nAs expected: the gate DID catch {len(regressions)} regression(s) "
            "caused by the broken prompt. Re-run with `python run_regression.py "
            "--gate` to see this as a non-zero exit code."
        )
    else:
        print(
            "\nUnexpected: no regression was detected. The Hallucination / "
            "PolicyAdherence judges may not have picked up the injected "
            "prompt break this run — try re-running once (LLM judges have "
            "some run-to-run variance)."
        )


if __name__ == "__main__":
    main()
