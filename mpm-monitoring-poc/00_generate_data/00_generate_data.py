# -*- coding: utf-8 -*-
"""
Step 00 -- Generate Synthetic Data

This is the ONLY place in the whole PoC where synthetic data is generated or
the demand-forecasting model is trained/scored. Steps 01-05 each demonstrate
one specific Comet MPM / Model Registry SDK call -- they load the files this
script writes to `data/` and must never regenerate or duplicate this logic
themselves. Run this once, first, before any other step.

Produces (all under `data/`, gitignored -- see config.py for exact paths):
  - training_data.csv         Clean historical training rows (every feature
                               fully populated, wide healthy inventory range).
  - training_baseline.csv     The SAME training rows, reshaped into the
                               `predictionId` / `feature_*` / `prediction_*`
                               column layout `CometMPM.upload_dataset_csv(...,
                               dataset_type="TRAINING_EVENTS")` expects
                               (Step 01 uploads this file as-is).
  - production_stream.csv     30 simulated days of production traffic, with a
                               synthetic upstream break injected at
                               `config.BREAK_DAY` and fixed at
                               `config.RETRAIN_DAY` (see below). Includes both
                               `warehouse_inventory_level` (what the model
                               actually saw -- possibly frozen/broken) and
                               `true_inventory_level` (the real physical
                               value, never sent to MPM) so the "how bad did
                               the break actually make things" comparison is
                               reproducible.
  - production_predictions.csv  `production_stream.csv` plus the trained
                               model's `predicted_units` for every row and a
                               computed `label_timestamp` (when that row's
                               ground truth would realistically become known).
                               This is the file Step 01 iterates over to build
                               MPM log_event() payloads.
  - model.joblib               The trained scikit-learn/XGBoost pipeline.
                               Step 04 uploads this same artifact under two
                               Model Registry versions (1.0.0 and 1.1.0) --
                               the point of that step is real version
                               history correlated with the incident, not a
                               numerically different model, so one trained
                               pipeline is enough.

The story (same shape as `MPM/pharma-demand-forecasting`, whose proven
mechanics this reuses): a distributor forecasts weekly reorder demand for its
distribution centers (DCs). An upstream ERP/warehouse-management-system
migration silently breaks one input feature (`warehouse_inventory_level`
collapses to a constant placeholder) and partially breaks another
(`lead_time_days` goes missing). A few days later the team notices the drift
alert, fixes the upstream feed, and redeploys -- that redeploy is what Step 04
registers as Model Registry version 1.1.0.

Usage:
    python 00_generate_data/00_generate_data.py
"""
import math
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

import config


# ---------------------------------------------------------------------------
# Feature/demand simulation
# ---------------------------------------------------------------------------
def _season_index(day: int) -> float:
    return 0.5 + 0.5 * math.sin(2 * math.pi * day / 30 + 0.4)


def _true_inventory_level(day: int, rng: np.random.Generator) -> float:
    """Real, physical inventory level -- deliberately WIDE (+/-200, plus
    noise) so the post-break collapse to a single frozen point produces a
    strong distributional (EMD/PSI/KL) signal. A narrow healthy range makes
    the break visually unremarkable in the drift charts."""
    base_cycle = 500 + 200 * math.sin(2 * math.pi * day / 14)
    post_break_drift = 0.0
    if config.BREAK_DAY <= day < config.RETRAIN_DAY:
        post_break_drift = 12.0 * (day - config.BREAK_DAY)
    noise = rng.normal(0, 50)
    return float(np.clip(base_cycle + post_break_drift + noise, 100, 1200))


def _demand_units(region, category, promo_flag, season_index, price_index,
                   days_since_last_shipment, true_inventory_level, rng):
    base = config.BASE_DEMAND[category] * config.REGION_MULTIPLIER[region]
    season_mult = 0.7 + 0.6 * season_index
    promo_mult = 1.25 if promo_flag else 1.0
    price_mult = float(np.clip(2.0 - price_index, 0.7, 1.3))
    inventory_mult = float(np.clip(1.0 - 0.0012 * (true_inventory_level - 500), 0.5, 1.6))
    cadence_mult = float(np.clip(1.0 + 0.01 * (days_since_last_shipment - 7), 0.8, 1.2))
    mean_demand = base * season_mult * promo_mult * price_mult * inventory_mult * cadence_mult
    noise = rng.normal(0, mean_demand * 0.05)
    return float(max(0.0, mean_demand + noise))


def _sample_common_fields(rng: np.random.Generator, day: int):
    region = rng.choice(config.REGIONS)
    category = rng.choice(config.PRODUCT_CATEGORIES)
    promo_flag = int(rng.random() < 0.15)
    season_index = _season_index(day)
    price_index = float(np.clip(rng.normal(1.0, 0.05), 0.8, 1.2))
    days_since_last_shipment = float(np.clip(rng.normal(7, 2.5), 1, 21))
    lead_time_mean = {"OTC": 4, "Rx": 9, "Medical_Supplies": 6}[category]
    lead_time_days = float(max(1, rng.poisson(lead_time_mean)))
    return region, category, promo_flag, season_index, price_index, days_since_last_shipment, lead_time_days


def generate_training_data(rng: np.random.Generator) -> pd.DataFrame:
    """Clean historical dataset -- every feature fully populated, wide
    healthy inventory range. Teaches the model the real relationship."""
    rows = []
    for _ in range(config.N_TRAINING_ROWS):
        day = int(rng.integers(0, 365))
        region, category, promo_flag, season_index, price_index, days_since_last_shipment, lead_time_days = (
            _sample_common_fields(rng, day)
        )
        true_inventory = float(np.clip(500 + 100 * math.sin(2 * math.pi * day / 14) + rng.normal(0, 120), 100, 1000))
        observed_inventory = float(max(0.0, true_inventory + rng.normal(0, 10)))
        demand_units = _demand_units(region, category, promo_flag, season_index, price_index,
                                      days_since_last_shipment, true_inventory, rng)
        rows.append({
            "region": region,
            "product_category": category,
            "promo_flag": promo_flag,
            "season_index": round(season_index, 4),
            "price_index": round(price_index, 4),
            "days_since_last_shipment": round(days_since_last_shipment, 2),
            "warehouse_inventory_level": round(observed_inventory, 2),
            "lead_time_days": lead_time_days,
            "demand_units": round(demand_units, 2),
        })
    return pd.DataFrame(rows)


def generate_production_stream(rng: np.random.Generator) -> pd.DataFrame:
    """Simulated production window with the break (BREAK_DAY) and the
    retrain/fix (RETRAIN_DAY) both injected."""
    end_time = time.time()
    start_time = end_time - config.N_DAYS * 86400
    seconds_per_event = 86400 / config.EVENTS_PER_DAY

    rows = []
    for day in range(config.N_DAYS):
        is_broken = config.BREAK_DAY <= day < config.RETRAIN_DAY
        is_post_retrain = day >= config.RETRAIN_DAY
        model_version = config.MPM_MODEL_VERSION_AFTER if is_post_retrain else config.MPM_MODEL_VERSION_BEFORE
        true_inventory_today = _true_inventory_level(day, rng)

        for _ in range(config.EVENTS_PER_DAY):
            region, category, promo_flag, season_index, price_index, days_since_last_shipment, lead_time_days = (
                _sample_common_fields(rng, day)
            )
            true_inventory_event = float(max(0.0, true_inventory_today + rng.normal(0, 8)))

            if is_broken:
                # Upstream ERP migration writes a frozen default placeholder.
                observed_inventory = config.FROZEN_INVENTORY_VALUE
            else:
                # Healthy (pre-break) OR fixed (post-retrain) -- real reading.
                observed_inventory = float(max(0.0, true_inventory_event + rng.normal(0, 10)))

            if is_broken and rng.random() < config.POST_BREAK_MISSING_LEAD_TIME_RATE:
                lead_time_days = np.nan

            demand_units = _demand_units(region, category, promo_flag, season_index, price_index,
                                          days_since_last_shipment, true_inventory_event, rng)
            timestamp = start_time + day * 86400 + rng.uniform(0, seconds_per_event) + \
                (rows.__len__() % config.EVENTS_PER_DAY) * seconds_per_event

            rows.append({
                "event_id": str(uuid.uuid4()),
                "timestamp": round(timestamp, 3),
                "day_index": day,
                "region": region,
                "product_category": category,
                "promo_flag": promo_flag,
                "season_index": round(season_index, 4),
                "price_index": round(price_index, 4),
                "days_since_last_shipment": round(days_since_last_shipment, 2),
                "warehouse_inventory_level": round(observed_inventory, 2),
                "lead_time_days": lead_time_days,
                "true_inventory_level": round(true_inventory_event, 2),
                "demand_units": round(demand_units, 2),
                "is_post_break": is_broken or is_post_retrain,
                "model_version": model_version,
            })

    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def write_training_baseline_csv(training_data: pd.DataFrame) -> None:
    """Reshapes the clean training rows into the column layout
    `CometMPM.upload_dataset_csv(..., dataset_type="TRAINING_EVENTS")` expects:
    a `predictionId` column, one `feature_<name>` column per input feature,
    and one `prediction_<name>` column per model output. Step 01 uploads this
    file byte-for-byte -- no reshaping happens there."""
    baseline = pd.DataFrame({
        "predictionId": [str(uuid.uuid4()) for _ in range(len(training_data))],
        "feature_region": training_data["region"],
        "feature_product_category": training_data["product_category"],
        "feature_promo_flag": training_data["promo_flag"],
        "feature_season_index": training_data["season_index"],
        "feature_price_index": training_data["price_index"],
        "feature_days_since_last_shipment": training_data["days_since_last_shipment"],
        "feature_warehouse_inventory_level": training_data["warehouse_inventory_level"],
        "feature_lead_time_days": training_data["lead_time_days"],
        "prediction_predicted_units": training_data["demand_units"],
    })
    baseline.to_csv(config.TRAINING_BASELINE_CSV, index=False)


# ---------------------------------------------------------------------------
# Model training + scoring
# ---------------------------------------------------------------------------
def build_pipeline() -> Pipeline:
    from xgboost import XGBRegressor

    preprocess = ColumnTransformer(transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), config.CATEGORICAL_FEATURES),
        ("num", SimpleImputer(strategy="median"), config.NUMERIC_FEATURES),
    ])
    model = XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, random_state=config.RANDOM_SEED,
    )
    return Pipeline(steps=[("preprocess", preprocess), ("model", model)])


def train_and_score(training_data: pd.DataFrame, production_stream: pd.DataFrame):
    """Trains on the clean historical data, scores the (partly broken)
    production stream, and stamps each row with the `label_timestamp` at
    which its ground truth would realistically become known -- this is what
    lets Step 01 decide, per event, whether to bundle a `labels=` payload."""
    import joblib

    pipeline = build_pipeline()
    pipeline.fit(training_data[config.FEATURE_COLUMNS], training_data[config.TARGET_COLUMN])
    joblib.dump(pipeline, config.MODEL_PATH)

    production_stream = production_stream.copy()
    production_stream["predicted_units"] = pipeline.predict(production_stream[config.FEATURE_COLUMNS])
    production_stream["label_timestamp"] = production_stream["timestamp"] + config.LABEL_DELAY_DAYS * 86400
    production_stream.to_csv(config.PRODUCTION_PREDICTIONS_CSV, index=False)

    def _rmse(mask):
        subset = production_stream[mask]
        if not len(subset):
            return float("nan")
        return float(np.sqrt(mean_squared_error(subset["demand_units"], subset["predicted_units"])))

    day = production_stream["day_index"]
    pre_rmse = _rmse(day < config.BREAK_DAY)
    broken_rmse = _rmse((day >= config.BREAK_DAY) & (day < config.RETRAIN_DAY))
    post_retrain_rmse = _rmse(day >= config.RETRAIN_DAY)
    return production_stream, pre_rmse, broken_rmse, post_retrain_rmse


def main():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config.RANDOM_SEED)

    print(f"Generating {config.N_TRAINING_ROWS} clean training rows + "
          f"{config.N_DAYS}x{config.EVENTS_PER_DAY} production events "
          f"(break on day {config.BREAK_DAY}, retrain on day {config.RETRAIN_DAY})...")

    training_data = generate_training_data(rng)
    training_data.to_csv(config.TRAINING_DATA_CSV, index=False)
    write_training_baseline_csv(training_data)

    production_stream = generate_production_stream(rng)
    production_stream.to_csv(config.PRODUCTION_STREAM_CSV, index=False)

    scored, pre_rmse, broken_rmse, post_retrain_rmse = train_and_score(training_data, production_stream)

    n_frozen = (scored["warehouse_inventory_level"] == config.FROZEN_INVENTORY_VALUE).sum()
    n_missing_lead_time = scored["lead_time_days"].isna().sum()
    n_with_label = (scored["label_timestamp"] <= time.time()).sum()

    print("\nWrote:")
    print(f"  {config.TRAINING_DATA_CSV.relative_to(config.ROOT_DIR)}          ({len(training_data)} rows)")
    print(f"  {config.TRAINING_BASELINE_CSV.relative_to(config.ROOT_DIR)}       ({len(training_data)} rows)")
    print(f"  {config.PRODUCTION_STREAM_CSV.relative_to(config.ROOT_DIR)}      ({len(scored)} rows)")
    print(f"  {config.PRODUCTION_PREDICTIONS_CSV.relative_to(config.ROOT_DIR)}  ({len(scored)} rows)")
    print(f"  {config.MODEL_PATH.relative_to(config.ROOT_DIR)}")

    print("\nSanity check (local only -- confirms the simulation shape before any step logs to Comet):")
    print(f"  rows with frozen warehouse_inventory_level ({config.FROZEN_INVENTORY_VALUE}): {n_frozen}")
    print(f"  rows missing lead_time_days                                : {n_missing_lead_time}")
    print(f"  rows old enough to already have a ground-truth label       : {n_with_label} / {len(scored)}")
    print(f"  pre-break RMSE    (true demand vs. predicted_units): {pre_rmse:.1f} units")
    print(f"  during-break RMSE (true demand vs. predicted_units): {broken_rmse:.1f} units")
    print(f"  post-retrain RMSE (true demand vs. predicted_units): {post_retrain_rmse:.1f} units")
    print("  -> during-break error should be visibly worse than pre-break, recovering post-retrain.")

    print("\nData generation complete. Proceed to 01_drift_and_missing_values/01_drift_and_missing_values.py.")


if __name__ == "__main__":
    main()
