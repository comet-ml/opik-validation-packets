# Step 06 — Regression Gate: UI Checklist

**Docs:** [Evaluate your LLM application](https://www.comet.com/docs/opik/v1/evaluation/evaluate_your_llm/)

1. Run `python 06_regression/run_regression.py` (report only).
2. Run `python 06_regression/simulate_config_regression.py` to inject a broken docs_rag prompt and confirm the gate catches it.
3. Run `python 06_regression/run_regression.py --gate; echo "exit=$?"` — immediately after step 2, while the effect may still be visible in a fresh run (note: the broken prompt is restored after step 2 finishes, so this specific invocation is expected to pass; it's `simulate_config_regression.py`'s own inline check that demonstrates the gate catching the injected break within the same process).
4. Read `schedule_example.py` (reference only — not executed).

In the Opik UI > Experiments:

- [ ] A `docs_rag-regression-check` experiment appears for each run
- [ ] Each has `<metric>_mean`, `<metric>_ci_low`, `<metric>_ci_high` experiment-level scores (from `bootstrap_summary`)
- [ ] Each has `<metric>_delta`, `<metric>_p_value`, `<metric>_significant`, `<metric>_effect_size` experiment-level scores (from `compare_to_baseline`), compared against `docs_rag-baseline` from Step 04
- [ ] During `simulate_config_regression.py`, the terminal output confirms at least one regression was detected (typically `hallucination` and/or `policy_adherence`)

Proceed to `07_annotation_queue/07_annotation_queue.py`.
