# Step 04 — Experiments: UI Checklist

**Docs:** [Evaluate your LLM application](https://www.comet.com/docs/opik/v1/evaluation/evaluate_your_llm/)

Run `python 04_experiments/04_experiments.py`, then verify in Opik UI > Experiments.

- [ ] An experiment named `docs_rag-baseline` appears
- [ ] It is pinned to the docs_rag dataset's current version (from Step 02)
- [ ] Every item has `hallucination`, `policy_adherence`, AND `retrieval_grounding` scores
- [ ] Clicking any experiment row opens the full trace tree (gateway span + nested docs_rag span)
- [ ] `experiment_config` on the run shows `orchestration_framework: custom` and the model used

Proceed to `05_benchmarking/05_benchmarking.py`.
