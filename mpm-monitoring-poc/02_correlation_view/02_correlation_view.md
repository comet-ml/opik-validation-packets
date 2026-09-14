# Step 02 — Accuracy / Distribution / Drift Correlation View: UI Checklist

**Success criterion:** Accuracy, output distribution, and drift shown as synchronized panels on
one page for visual correlation. **Success:** all three signals viewable together, synced to the
same time range and model version. **Test:** confirm the Model Performance page displays all
three signals in sync; optionally build a custom panel for a single combined timeline.

**Docs:** [Custom metrics](https://www.comet.com/docs/v2/guides/model-production-monitoring/custom-metrics/) /
[MPM UI](https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/#model-performance-page)

**Prerequisite:** `00_generate_data/00_generate_data.py` and `01_drift_and_missing_values.py` (live,
not `--dry-run`) must have already run — this step's UI checklist reads real logged data.

## Run it

```bash
python 02_correlation_view/02_correlation_view.py
```

- [ ] Prints a local day-by-day MAE table and confirms the last labeled day is before
  `BREAK_DAY` — i.e. nothing about the incident has a confirmed accuracy number yet

## One-time setup

1. Go to the model's **Settings** tab > **Custom Metrics** > **+ Add Metric**, name it
   `Accuracy (MAE)`, and paste this SQL. This is required — there is no built-in "Accuracy"
   panel, only built-in Output Distribution and Input Drift panels.
   ```sql
   SELECT MAE("prediction_predicted_units", "label_value_actual_units") FROM MODEL
   ```

## Verify in the UI

Open the **Model Performance** page for `demand-forecast-poc`.

- [ ] All three panels — **Accuracy (MAE)** (custom metric), **Output Distribution**
  (`predicted_units`), **Input Drift** (aggregate) — are visible on the same page
- [ ] Changing the date-range selector moves all three panels together (synced time range)
- [ ] Selecting a specific `model_version` (`1.0.0` vs `1.1.0`) filters all three panels together
  (synced model version) — see Step 04 for what those two versions represent
- [ ] Accuracy's line visibly stops several days before "today"; Distribution and Drift both run
  all the way to "today" — this is the visual proof of Step 01's "no ground truth yet" pitch
- [ ] (Optional, if time allows) Build one custom panel combining Accuracy + a drift metric on a
  single timeline, rather than switching between two panels

Proceed to `03_alerting/03_alerting.py`.
