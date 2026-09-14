# Step 03 — Metrics: Checklist

**Docs:** [Metrics overview](https://www.comet.com/docs/opik/v1/evaluation/metrics/overview/)

Run `python 03_metrics/03_metrics.py`. This step has no UI component — it validates the metric
implementations standalone against canned samples, before Step 04 wires them into a live
experiment loop.

- [ ] GOOD case: `hallucination` is closer to 0.0 than the BAD case's
- [ ] GOOD case: `policy_adherence` is closer to 1.0 than the BAD case's
- [ ] BAD case: `policy_adherence` reason mentions the fabricated policy detail and/or the fake action
- [ ] `RetrievalGrounding`: good retrieval scores 1.0, bad retrieval scores 0.0

Note: the two LLM-judge scores (`hallucination`, `policy_adherence`) can vary slightly between
runs — if a value looks off, re-run once before treating it as a metric bug.

Proceed to `04_experiments/04_experiments.py`.
