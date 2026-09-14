# Step 05 — Benchmarking: UI Checklist

**Docs:** [Evaluate your LLM application](https://www.comet.com/docs/opik/v1/evaluation/evaluate_your_llm/)

Run `python 05_benchmarking/05_benchmarking.py`, then verify in Opik UI > Experiments.

- [ ] 2 new experiments appear: `docs_rag-gpt-4o-mini`, `docs_rag-gpt-4o`
- [ ] Selecting both variants and comparing shows cost/latency/quality side by side
- [ ] The `gpt-4o` variant costs more per item than `gpt-4o-mini` (Cost column)
- [ ] Quality metrics (`hallucination`, `policy_adherence`, `retrieval_grounding`) are similar or better on `gpt-4o` — if not, that's a legitimate finding worth flagging to the customer, not a bug

TODO(SE): swap `MODEL_VARIANTS` (in `05_benchmarking.py`) for the real customer's actual model
tiers before using this step in a live benchmarking conversation — including non-OpenAI providers, e.g.
`anthropic/claude-haiku-4-5` (needs `ANTHROPIC_API_KEY`; see `llm_clients.py` for the direct-SDK
dispatch that makes this a config-only change, no code change, once a key is available).

Proceed to `06_regression/run_regression.py`.
