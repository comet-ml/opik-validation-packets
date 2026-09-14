"""
Step 05 -- Custom Metric Segmentation

SDK/product mechanic demonstrated: the same Custom Metric SQL dialect from
Step 02, extended with a `WHERE` predicate on a `feature_<name>` column --
this is how any already-logged input feature becomes a segmentable
dimension, with no additional logging call required. Example SQL (static --
it never depends on what's actually in `data/`, so it lives in
`05_segmentation.md` instead of being printed here) lives there.

The `feature_region` column exists purely because Step 01's
`input_features={"region": ..., ...}` dict had a `region` key -- MPM
generates one `feature_<name>` column per input-feature key automatically,
so any categorical field logged this way is filterable the same way, with no
schema declared up front. `WHERE` predicates on a Custom Metric are just
plain equality/comparison filters over those columns; there's nothing
region-specific about the mechanism.

In practice you rarely need one Custom Metric per segment value -- the
Model Performance page has a built-in segment/region **filter control** that
applies the same predicate to every panel (Accuracy, Distribution, Drift) at
once. The per-region SQL is shown mainly to make the underlying mechanic
explicit; the filter dropdown is the faster way to actually use it.

Nothing new is sent to Comet in this step -- Step 01 already logged `region`
as an input feature on every event. What this script does is recompute the
region-segmented MAE locally from `data/production_predictions.csv` (written
by Step 00) -- a no-credentials-required check that the segments actually
differ enough to be worth filtering by. Unlike the SQL, this changes every
time Step 00 regenerates data, so it's worth computing fresh.

Docs: https://www.comet.com/docs/v2/guides/model-production-monitoring/custom-metrics/#custom-metrics-for-a-subset-of-predictions

Usage:
    python 05_segmentation/05_segmentation.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import config


def local_mae_by_region() -> pd.DataFrame:
    df = pd.read_csv(config.PRODUCTION_PREDICTIONS_CSV)
    now = time.time()
    labeled = df[df["label_timestamp"] <= now].copy()
    labeled["abs_error"] = (labeled["demand_units"] - labeled["predicted_units"]).abs()
    return labeled.groupby("region")["abs_error"].mean().rename("mae").reset_index().sort_values("mae")


def main():
    if not config.PRODUCTION_PREDICTIONS_CSV.exists():
        raise SystemExit("Missing data/production_predictions.csv -- run 00_generate_data first.")

    by_region = local_mae_by_region()
    print("Locally reconstructed MAE by region (labeled events only):")
    print(by_region.to_string(index=False))
    print(
        "\nAny logged input feature works the same way -- `product_category` in this dataset is "
        "just as filterable; a real deployment might segment by business unit or customer tier "
        "instead. Nothing about the mechanism is specific to `region`."
    )
    print("\nSee 05_segmentation.md for the example SQL and the full UI checklist.")


if __name__ == "__main__":
    main()
