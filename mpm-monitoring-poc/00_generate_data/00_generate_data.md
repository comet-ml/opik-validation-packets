# Step 00 — Generate Synthetic Data

Not one of the 5 MPM success criteria — this is the one-time data-prep step every other step
depends on. It generates the clean training dataset, the `upload_dataset_csv`-ready training
baseline, and the 30-day simulated production stream (break + retrain + true-vs-observed values),
then trains and scores the demand-forecasting model. No Comet SDK calls happen here — this step
never touches the network.

## Run it

```bash
python 00_generate_data/00_generate_data.py
```

No flags, no credentials required.

- [ ] Prints the 5 files it wrote under `data/` (`training_data.csv`, `training_baseline.csv`,
  `production_stream.csv`, `production_predictions.csv`, `model.joblib`)
- [ ] Prints a local sanity check: during-break RMSE clearly higher than pre-break, post-retrain
  RMSE recovering back toward baseline — confirms the simulation is shaped correctly before any
  step tries to log it to Comet

## Why this step exists on its own

Steps 01–05 each exist to demonstrate one specific Comet SDK call (`log_event`,
`upload_dataset_csv`, `register_model`, custom-metric SQL). None of them should have to generate or
retrain anything to do that — they just load whatever this script already wrote to `data/`. If you
ever change the underlying simulation (not just re-running this script with the same logic), rerun
this step first — every later step will pick up the new files automatically.

Proceed to `01_drift_and_missing_values/01_drift_and_missing_values.py`.
