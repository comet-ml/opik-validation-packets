# Step 07 — Annotation Queue: UI Checklist

**Docs:** [Annotation queues](https://www.comet.com/docs/opik/v1/production/annotation_queues/)

Run `python 06_regression/simulate_config_regression.py` first (if you haven't already) to
guarantee at least one flagged item, then run `python 07_annotation_queue/07_annotation_queue.py`.

Verify in Opik UI:

- [ ] Feedback definitions `root_cause` (categorical) and `severity` (numeric, 1-5) exist under Configuration > Feedback definitions
- [ ] A traces annotation queue named `GenAI Gateway Regression Review` exists
- [ ] The queue contains at least 1 item (the trace(s) flagged by the injected regression)
- [ ] Opening the queue and clicking into an item shows the `root_cause` and `severity` scoring widgets
- [ ] Submitting a manual annotation (e.g. `root_cause=hallucination`, `severity=3`) is saved and visible on the trace

Proceed to `08_dashboard/08_dashboard.py`.
