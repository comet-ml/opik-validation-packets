# Step 02 — Datasets: UI Checklist

**Docs:** [Manage datasets](https://www.comet.com/docs/opik/v1/evaluation/manage_datasets/)

Run `python 02_datasets/02_datasets.py`, then verify in Opik UI > Datasets.

- [ ] `genai-gateway-docs-rag-qa` exists with 7 items (6 seed + 1 inserted), at least 3 versions, each item has a `relevant_doc_ids` field
- [ ] In the version history, the first item's `expected_output` reflects the mutation-1 update text
- [ ] The inserted mutation-2 item is visible in the current version of the dataset

Proceed to `03_metrics/03_metrics.py`.
