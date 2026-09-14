"""
Step 02 -- Accuracy / Distribution / Drift Correlation View

SDK/product mechanic demonstrated: Custom Metric SQL. There is no built-in
"Accuracy" panel in MPM -- only built-in Output Distribution and Input Drift
panels. An accuracy metric has to be defined once, up front, as a Custom
Metric (model > Settings > Custom Metrics > + Add Metric), using a small
pseudo-SQL dialect that runs against a fixed virtual table called `MODEL`:

    SELECT MAE("prediction_predicted_units", "label_value_actual_units") FROM MODEL

Column-naming convention (this is what makes the SQL "just work" once
`log_event(...)` has logged data -- see Step 01):
  - `prediction_<name>` -- one column per key in `output_features={...}`
  - `label_value_<name>` -- one column per key in `labels={...}`, but ONLY
    for events where a label was actually bundled in (a `MAE` aggregate
    silently skips rows where the column is null, which is exactly what
    makes this metric automatically "run out" a few days before "today" --
    see the printed sanity check below)
  - `feature_<name>` -- one column per key in `input_features={...}`
    (used for segmentation/filtering -- see Step 05)

Nothing new is sent to Comet in this step -- Step 01 already logged every
event this metric reads. The exact SQL to paste into Settings lives in
`02_correlation_view.md` (it's static -- it never depends on what's actually
in `data/`, so there's no reason to print it from a script). What this
script does instead is recompute, locally from
`data/production_predictions.csv` (written by Step 00), the daily MAE the
Accuracy panel *should* show once that metric exists -- a
no-credentials-required check that there is a real accuracy signal to look
at, and that (as expected) it stops several days before "today". Unlike the
SQL, this number changes every time Step 00 regenerates data, so it's worth
computing fresh rather than writing down once.

Docs: https://www.comet.com/docs/v2/guides/model-production-monitoring/custom-metrics/
      https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/#model-performance-page

Usage:
    python 02_correlation_view/02_correlation_view.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import config


def local_accuracy_by_day() -> pd.DataFrame:
    """Reproduces what the Accuracy (MAE) custom metric will show once
    labels have arrived -- computed here against the LOCAL csv (which has
    every label, since it's the synthetic ground truth) filtered down to
    only the events that would actually have a label bundled in by now, so
    the printed table matches what MPM itself can currently see."""
    df = pd.read_csv(config.PRODUCTION_PREDICTIONS_CSV)
    now = time.time()
    labeled = df[df["label_timestamp"] <= now].copy()
    labeled["abs_error"] = (labeled["demand_units"] - labeled["predicted_units"]).abs()
    by_day = labeled.groupby("day_index")["abs_error"].mean().rename("mae").reset_index()
    return by_day


def main():
    if not config.PRODUCTION_PREDICTIONS_CSV.exists():
        raise SystemExit("Missing data/production_predictions.csv -- run 00_generate_data first.")

    by_day = local_accuracy_by_day()
    last_labeled_day = int(by_day["day_index"].max()) if len(by_day) else -1
    print("Locally reconstructed daily MAE (only days with an available label as of now):")
    print(by_day.tail(10).to_string(index=False))
    print(f"\nLast day with ANY label available: day {last_labeled_day} of {config.N_DAYS - 1}")
    print(f"Break day: {config.BREAK_DAY}  |  Retrain day: {config.RETRAIN_DAY}")
    if last_labeled_day < config.BREAK_DAY:
        print(
            "-> Confirmed: MAE('...') FROM MODEL has zero rows to average over the break/retrain "
            "period yet (every label_value_actual_units there is still null) -- Input Drift (Step "
            "01) is the only signal currently available for this incident."
        )

    print("\nSee 02_correlation_view.md for the metric SQL to create and the full UI checklist.")


if __name__ == "__main__":
    main()
