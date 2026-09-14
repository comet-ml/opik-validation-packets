"""
Step 03 -- Threshold-Based Alerting

SDK/product mechanic demonstrated: none, on purpose -- there is no SDK/REST
call for creating an MPM alert rule (confirmed against `comet_ml.API` and the
MPM REST endpoints doc). Alert rules are configured through the UI only:
model > **Alerts** page > **+ Add Alert Rule**, picking a metric (e.g. Input
Drift EMD on a specific feature), a threshold, and an optional evaluation
delay / segment filter.

What this script does instead is ground that UI decision in real numbers, so
you're not picking a threshold blind: it recomputes, locally, the same drift
metric MPM's Input Drift tab plots for `warehouse_inventory_level` -- Earth
Mover's Distance (EMD) against the training baseline -- aggregated per period
(pre-break / during-break / post-retrain) from the data
`00_generate_data/00_generate_data.py` already wrote to `data/`.

NOTE: this aggregates EMD over each whole period, not day-by-day. At this
demo's synthetic volume (a few dozen events/day), a single day's EMD against
the full training baseline is dominated by sampling noise, not signal --
aggregating first is what makes the pre-break vs. during-break contrast
reliable locally. The real MPM dashboard has its own (undocumented)
day-bucketing behavior for the Input Drift chart -- use this script's numbers
as a directional sanity check that the break is a real, large jump, not as a
literal prediction of the exact number the live chart will show per day.

Docs: https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/#alerts-page

Usage:
    python 03_alerting/03_alerting.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from scipy.stats import wasserstein_distance

import config


def emd_by_period() -> dict:
    """Same drift metric MPM's Input Drift tab computes (Earth Mover's
    Distance) for `warehouse_inventory_level`, recomputed locally against the
    training baseline distribution -- aggregated per period rather than per
    day (see module docstring for why)."""
    training = pd.read_csv(config.TRAINING_DATA_CSV)
    baseline = training["warehouse_inventory_level"].to_numpy()
    stream = pd.read_csv(config.PRODUCTION_STREAM_CSV)

    day = stream["day_index"]
    periods = {
        f"pre-break (days 0-{config.BREAK_DAY - 1})": stream[day < config.BREAK_DAY],
        f"during-break (days {config.BREAK_DAY}-{config.RETRAIN_DAY - 1})": stream[
            (day >= config.BREAK_DAY) & (day < config.RETRAIN_DAY)
        ],
        f"post-retrain (days {config.RETRAIN_DAY}-{config.N_DAYS - 1})": stream[day >= config.RETRAIN_DAY],
    }
    return {
        label: round(float(wasserstein_distance(baseline, group["warehouse_inventory_level"].to_numpy())), 1)
        for label, group in periods.items()
    }


def main():
    if not config.PRODUCTION_STREAM_CSV.exists() or not config.TRAINING_DATA_CSV.exists():
        raise SystemExit("Missing data/*.csv -- run 00_generate_data first.")

    emd = emd_by_period()
    print("warehouse_inventory_level EMD vs. training baseline, aggregated per period:")
    for label, value in emd.items():
        print(f"  {label:<45}: {value}")

    pre_emd = list(emd.values())[0]
    broken_emd = list(emd.values())[1]
    ratio = broken_emd / pre_emd if pre_emd else float("inf")
    print(f"\nDuring-break EMD is ~{ratio:.1f}x the pre-break EMD.")
    print(
        "Use this to pick a threshold between the pre-break and during-break numbers you see "
        "live in Features > warehouse_inventory_level > Drift (Step 01) -- do not treat these "
        "exact numbers as what the live per-day chart will show (see module docstring)."
    )
    print("\nSee 03_alerting.md for how to create the alert rule and the UI checklist.")


if __name__ == "__main__":
    main()
