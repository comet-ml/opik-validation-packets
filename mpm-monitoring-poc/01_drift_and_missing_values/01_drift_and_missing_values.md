# Step 01 — Automated Drift & Missing-Value Tracking: UI Checklist

**Success criterion:** Drift and missing-value metrics computed automatically without ground
truth labels, across all model types. **Success:** drift/missing-value metrics computed with no
manual baseline required; a configured threshold alert notifies on a defined change. **Test:**
simulate a missing-value or distribution-shift scenario; confirm the metric is computed
automatically and a configured alert fires on it (alert wiring itself is Step 03).

**Docs:** [Sending data to MPM](https://www.comet.com/docs/v2/guides/model-production-monitoring/send-mpm-data/) /
[MPM UI](https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/)

**Prerequisite:** `python 00_generate_data/00_generate_data.py` (once, before this step).

## Run it

```bash
python 01_drift_and_missing_values/01_drift_and_missing_values.py --dry-run   # no credentials needed
python 01_drift_and_missing_values/01_drift_and_missing_values.py            # sends to Comet MPM
```

- [ ] `--dry-run` prints an example event payload with a bundled `labels` key and one without, plus
  counts of bundled labels / missing `lead_time_days` / events per `model_version` — confirms the
  event shapes are correct before sending anything to Comet
- [ ] Live run reports "All events sent successfully"

## One-time setup (do this once per fresh model, before checking drift)

1. Open the model's **Settings** tab in Comet MPM and select
   `demand-forecast-poc-training-baseline-v1` (or whatever `MPM_TRAINING_DATASET_NAME`
   resolves to) as the **drift baseline**. Without this, drift defaults to period-over-period
   comparison, which for a feature that freezes to a constant actually *drops to zero* right after
   the break (every day looks identical to the day before it) — the opposite of what this step
   needs to show. See `README.md` ("Why the training-baseline upload matters").

## Verify in the UI

Open the Comet UI > your workspace > MPM > model `demand-forecast-poc`.

- [ ] **Features page > `warehouse_inventory_level` > Drift tab** — a step change in EMD/PSI/KL
  appears exactly at the break (day 24 of this window), with no manual baseline configuration
  beyond the one-time Settings step above
- [ ] **Features page > `warehouse_inventory_level` > Distribution tab** — histogram shows a wide,
  healthy spread pre-break collapsing to a single spike at `500` post-break
- [ ] **Features page > `lead_time_days` > Missing Values tab** — a spike in missing-value rate
  starting at the same break day
- [ ] All of the above is visible immediately, even though **no `demand_units` label exists yet**
  for any event in the last 7 days (`LABEL_DELAY_DAYS`) — confirm this by checking the **Model
  Performance page > Accuracy (MAE)** metric (see Step 02 for defining it) and noting its line
  stops several days before "today," while the drift/missing-value charts run all the way to
  "today"
- [ ] Drift recovers back toward the pre-break baseline starting day 27 (`RETRAIN_DAY`) — the
  same day Step 04 registers Model Registry version `1.1.0`

Proceed to `02_correlation_view/02_correlation_view.py`.
