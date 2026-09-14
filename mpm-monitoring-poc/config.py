# -*- coding: utf-8 -*-
"""
Shared constants for the MPM getting-started PoC.

The story (deliberately the same shape as `MPM/pharma-demand-forecasting`,
which this PoC reuses the proven mechanics of): a pharma distributor forecasts
weekly reorder demand for its distribution centers (DCs). An upstream
ERP/warehouse-management-system migration silently breaks one input feature
(`warehouse_inventory_level` collapses to a constant placeholder) and
partially breaks another (`lead_time_days` goes missing). A few days later,
the team notices the drift alert, fixes the upstream feed, and redeploys —
that redeploy is what Step 04 registers as a new Model Registry version.

This is intentionally leaner than `pharma-demand-forecasting` (shorter
window, fewer events, one break/one retrain instead of a full presentation
narrative) — it exists to give a fast, minimal walkthrough of the 5 MPM
success criteria, not a polished sales pitch.

All synthetic data generation and model training happens ONCE, in
`00_generate_data/00_generate_data.py` — every other step (01-05) only reads
the files it writes to `data/` (see DATA_DIR / *_CSV / MODEL_PATH below,
shared by every step). Steps 01-05 focus on the Comet SDK calls themselves
(log_event, upload_dataset_csv, register_model, custom-metric SQL), not on
data prep.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

TRAINING_DATA_CSV = DATA_DIR / "training_data.csv"
TRAINING_BASELINE_CSV = DATA_DIR / "training_baseline.csv"
PRODUCTION_STREAM_CSV = DATA_DIR / "production_stream.csv"
PRODUCTION_PREDICTIONS_CSV = DATA_DIR / "production_predictions.csv"
MODEL_PATH = DATA_DIR / "model.joblib"

# ---------------------------------------------------------------------------
# Domain / feature space (reused as-is from pharma-demand-forecasting — same
# proven feature set, same demand formula; only the volumes/window below are
# shrunk down for a "getting started" pace).
# ---------------------------------------------------------------------------
REGIONS = ["Northeast", "Midwest", "South", "West", "Southeast"]
PRODUCT_CATEGORIES = ["OTC", "Rx", "Medical_Supplies"]

# `region` is the dimension used to demonstrate Custom Metric Segmentation
# (Step 05) — any logged categorical feature would work the same way.
CATEGORICAL_FEATURES = ["region", "product_category"]
NUMERIC_FEATURES = [
    "promo_flag",
    "season_index",
    "price_index",
    "days_since_last_shipment",
    "warehouse_inventory_level",
    "lead_time_days",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "demand_units"

BASE_DEMAND = {"OTC": 850, "Rx": 420, "Medical_Supplies": 260}
REGION_MULTIPLIER = {
    "Northeast": 1.15,
    "Midwest": 0.95,
    "South": 1.05,
    "West": 1.10,
    "Southeast": 0.90,
}

# ---------------------------------------------------------------------------
# Simulation window
# ---------------------------------------------------------------------------
N_DAYS = 30  # simulated production window, ending "today" — half of pharma-demand-forecasting's 60
EVENTS_PER_DAY = 40
N_TRAINING_ROWS = 2000
RANDOM_SEED = 42

# How many days after a prediction is logged before its ground-truth label
# becomes available (mirrors real-world delayed reorder-cycle ground truth).
LABEL_DELAY_DAYS = 7

# The upstream data break happens at this day index (0 = first day of the
# window, N_DAYS - 1 = last day / "today"). Must be strictly greater than
# (N_DAYS - 1 - LABEL_DELAY_DAYS) so that every post-break prediction is
# still inside the current "no label yet" window as of "today" — i.e. there
# is zero confirmed accuracy data anywhere in the post-break period yet, not
# just for the last few days of it. See pharma-demand-forecasting/README.md
# ("Critical timing constraint") for why this was tested and is load-bearing:
# putting the break any earlier lets accuracy catch up on its own by "today"
# and undercuts the "drift is the only signal you have right now" pitch.
BREAK_DAY = N_DAYS - LABEL_DELAY_DAYS  # day 23 of 30 -- right at the label-delay edge,
# maximizing how many broken+retrained days fit inside the "no label yet" window while
# still leaving both periods (broken, then fixed) with enough days to sample cleanly.

# The team notices the drift (Step 01/03) and redeploys a fix a few days
# later — this is the retrain event Step 04 registers as Model Registry
# version 1.1.0. Still comfortably inside the LABEL_DELAY_DAYS window, so the
# "no ground truth yet" pitch holds for the entire post-break period,
# including the retrain — nobody has an accuracy number for any of this yet,
# only drift.
RETRAIN_DAY = BREAK_DAY + 4  # day 27 of 30 -- 3 days of "broken", then 3 days "fixed"

# The frozen placeholder value the corrupted ERP feed writes into every
# record after the migration — deliberately close to the healthy
# distribution's own mean (~500), not an obvious outlier. See
# pharma-demand-forecasting/README.md ("Why 500 and not an obvious outlier?")
# for the full reasoning: a plausible-looking value is what actually slips
# through undetected, and keeps the model's prediction error compounding
# gradually rather than jumping to an immediate cliff.
FROZEN_INVENTORY_VALUE = 500.0

# Fraction of post-break, pre-retrain records that also lose `lead_time_days`
# entirely (a second field mis-mapped by the same migration) — showcases
# MPM's missing-value tracking alongside feature drift.
POST_BREAK_MISSING_LEAD_TIME_RATE = 0.20

# ---------------------------------------------------------------------------
# Comet MPM model identity
# ---------------------------------------------------------------------------
MPM_MODEL_NAME = os.getenv("MPM_MODEL_NAME", "demand-forecast-poc")

# Tags every prediction event with which side of the retrain it belongs to.
# Deliberately the SAME strings used as Model Registry version numbers in
# Step 04, so the "which model version made this prediction" filter in the
# MPM UI and the Model Registry's version history are talking about the same
# two versions — that alignment is what makes the retrain-vs-incident
# timeline correlation in Step 04 concrete instead of just two unrelated
# numbers.
MPM_MODEL_VERSION_BEFORE = "1.0.0"
MPM_MODEL_VERSION_AFTER = "1.1.0"

# A training-dataset name is a separate object from the model itself and
# isn't cleaned up when the model is deleted via the Model Registry (see
# pharma-demand-forecasting/README.md "Resetting between presentations") —
# bump this suffix if you delete+recreate the model and re-upload.
MPM_TRAINING_DATASET_NAME = os.getenv(
    "MPM_TRAINING_DATASET_NAME", f"{MPM_MODEL_NAME}-training-baseline-v2"
)

# ---------------------------------------------------------------------------
# Comet Model Registry identity (Step 04 only)
# ---------------------------------------------------------------------------
# A registered model belongs to an Experiment Management project — separate
# from the MPM model's own page, but the registry model name is set to match
# MPM_MODEL_NAME (per Comet's own guidance: "you simply need to ensure that
# the model name used when sending MPM events matches up with the model name
# in the Model Registry" —
# https://www.comet.com/docs/v2/guides/model-production-monitoring/send-mpm-data/#integration-with-experiment-management).
COMET_PROJECT_NAME = os.getenv("COMET_PROJECT_NAME", "mpm-monitoring-poc")
