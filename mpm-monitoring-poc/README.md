# MPM Monitoring PoC — SDK Mechanics Walkthrough

A hands-on integration tutorial for Model Production Monitoring (MPM) success criteria —
focused on **how the Comet/MPM SDK is actually used**: the specific API calls, their parameters,
and why they're called the way they are. This is not a polished sales narrative (contrast with
`MPM/pharma-demand-forecasting`, whose proven mechanics this packet reuses directly, and which IS
built for that kind of presentation) — it's meant to read like documentation you'd hand an
engineer wiring this up for real.

`00_generate_data/` is the only place synthetic data is generated or the model is trained — it
exists purely so Steps 01-05 have something realistic to log, and none of that business logic gets
in the way of the SDK call each step is actually demonstrating. Run it once, first. Then work
through Steps 01-05 in order — each one consumes the files `00_generate_data` produced (or, for
Steps 02/05, the events Step 01 logged) rather than being disconnected scripts.

## The scenario

Same shape as `MPM/pharma-demand-forecasting` (deliberately — this reuses that demo's
extensively-validated mechanics rather than reinventing them): a distributor forecasts weekly
reorder demand for its distribution centers (DCs). An XGBoost regression model predicts
`predicted_units` from 8 input features (`region`, `product_category`, `promo_flag`,
`season_index`, `price_index`, `days_since_last_shipment`, `warehouse_inventory_level`,
`lead_time_days`). The demo simulates 30 days of production predictions ending "today":

- **Day 23 (`BREAK_DAY`)** — a synthetic upstream ERP/WMS migration collapses
  `warehouse_inventory_level` to a constant placeholder (`500.0`) and makes `lead_time_days` go
  missing for ~20% of records. The model never crashes — it just quietly gets worse, because it's
  reasoning from a frozen, stale input.
- **Day 27 (`RETRAIN_DAY`)** — the team notices the drift alert, fixes the upstream feed, and
  redeploys. This is the retrain event Step 04 registers as Model Registry version `1.1.0`.
  Predictions from this point on are tagged `model_version=1.1.0` in MPM (vs. `1.0.0` before).
- **"Today" (day 29)** — ground-truth labels (`actual_units`) are bundled directly into each
  prediction event once `LABEL_DELAY_DAYS` (7) has passed. Because `BREAK_DAY` is deliberately
  placed right at the edge of that 7-day window, **nothing** in the break-or-retrain period has a
  confirmed accuracy number yet, as of "today" — only drift does. This is what makes Step 01's "no
  ground truth yet" claim literal, not just narrative framing.

Local dry-run of this repo's own reference data shows a clean version of the story:

| Period | RMSE (true demand vs. predicted) | `warehouse_inventory_level` EMD vs. baseline |
|---|---|---|
| pre-break | ~45 units | ~40 |
| during-break | ~109 units | ~112 |
| post-retrain | ~43 units | ~53 |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in COMET_API_KEY / COMET_WORKSPACE in .env
```

> **Note:** MPM is a gated feature on Comet SaaS — if you don't see an MPM tab in your workspace,
> ask your Comet account team to enable it before running this demo end-to-end.

`.env` holds credentials only — everything else (model name, window length, break/retrain day,
etc.) is a plain constant in `config.py`, shared by every numbered step via
`sys.path.insert(0, str(Path(__file__).parent.parent))`.

## Running

Start with Step 00 — it has no flags and needs no credentials, since it never talks to Comet:

```bash
python 00_generate_data/00_generate_data.py
```

Every step after that is safe to run with **no Comet credentials at all** — each one either has an
explicit `--dry-run` flag or (Step 01) automatically falls back to dry-run behavior when
`COMET_API_KEY`/`COMET_WORKSPACE` aren't set. Test locally before sending anything to Comet.

| Step | SDK mechanic demonstrated | Script | Checklist |
|------|---|---|---|
| 00 | *(none — data prep only)* | `00_generate_data/00_generate_data.py` — the ONLY place data is generated or the model trained | `00_generate_data.md` |
| 01 | `CometMPM(...)`, `upload_dataset_csv(dataset_type="TRAINING_EVENTS")`, `log_event(..., labels=...)` | `01_drift_and_missing_values/01_drift_and_missing_values.py` — loads Step 00's data, builds event payloads, logs them | `01_drift_and_missing_values.md` |
| 02 | Custom Metric SQL (`prediction_<name>` / `label_value_<name>` columns) | `02_correlation_view/02_correlation_view.py` — prints the Accuracy custom-metric SQL + a local accuracy-timeline check | `02_correlation_view.md` |
| 03 | *(no SDK call — alert rules are UI-only)* | `03_alerting/03_alerting.py` — recomputes the drift signal locally to ground a threshold choice | `03_alerting.md` |
| 04 | `experiment.log_model(...)` → `experiment.register_model(version=..., registry_name=..., stages=...)` | `04_model_registry/04_model_registry.py` — registers versions `1.0.0`/`1.1.0` under the same registry name as the MPM model | `04_model_registry.md` |
| 05 | Custom Metric SQL with a `WHERE "feature_<name>" = '...'` predicate | `05_segmentation/05_segmentation.py` — prints segmented custom-metric SQL + a local MAE-by-region check | `05_segmentation.md` |

Each step's script has a module docstring explaining the SDK call(s) it demonstrates, their
important parameters, and why they're called the way they are. Each step also has a real UI
checklist in its `.md` file, restating the exact success/test language from the criteria doc at
the top.

## Why this reuses pharma-demand-forecasting's mechanics rather than reinventing them

Three load-bearing design choices are carried over as-is (see that repo's README for the full
reasoning and the live-debugging history behind each one):

- **Labels are bundled directly into prediction events** (`log_event(..., labels=...)`), not sent
  later as separate delayed events — Comet's daily label/prediction merge job was found unreliable
  in testing (labels sat unmerged for 2+ days). Bundling makes accuracy available immediately.
- **Uploading a training baseline isn't enough on its own** — `upload_dataset_csv(...,
  dataset_type="TRAINING_EVENTS")` only makes the dataset available; the model's **Settings** tab
  still needs it manually selected as the active drift baseline (Step 01's one-time setup — this
  trips people up, so it's called out explicitly in both the script's module docstring and the
  `.md` checklist). Without this, drift defaults to period-over-period comparison, which for a
  feature that freezes to a constant actually *drops to zero* right after the break.
- **The frozen value (`500.0`) is close to the healthy distribution's own mean, not an obvious
  outlier**, and the healthy pre-break distribution is deliberately WIDE — both are what make the
  break realistic (a plausible-looking wrong value is what actually slips through undetected) and
  keep the drift signal strong (collapsing a wide spread onto a point produces a much larger
  EMD/PSI/KL than collapsing a narrow one).
- **The break sits right at the edge of the label-delay window** (`BREAK_DAY = N_DAYS -
  LABEL_DELAY_DAYS`) so that, as of "today," zero post-break predictions have a label yet — this
  is what keeps the "drift is the only signal you have right now" pitch a *current*, undeniable
  claim rather than something accuracy would have already caught up on by the time anyone's
  looking at the dashboard.

## New in this PoC: Model Registry / version history (Step 04)

`pharma-demand-forecasting` doesn't cover this criterion — it's new design for this PoC. Comet's
Model Registry is a separate subsystem from MPM, but "each model in MPM has a corresponding model
in the Model Registry" (per Comet's own MPM UI docs), and the two are linked simply by using the
same name. Step 04 goes one step further and attaches real version history to that shared model:
`comet_ml.start()` → `experiment.log_model(...)` → `experiment.register_model(..., version=...,
registry_name=..., comment=..., stages=...)`, once for version `1.0.0` (the pre-incident
deployment) and once for `1.1.0` (the post-retrain redeploy). Both MPM's per-event
`model_version` tag and the registry's version numbers use the exact same two strings, so
filtering the MPM dashboard by version and reading the registry's version history describe the
same cutover — that alignment is what makes "did we retrain around when this started, and did it
help" answerable by looking, not by taking someone's word for it. Both versions log the same
`model.joblib` artifact on purpose — what this criterion tests is real, timestamped version
history correlated with an incident, not a numerically different model.

## Repo layout

```
mpm-monitoring-poc/
├── README.md
├── requirements.txt
├── .env.example
├── config.py                              # all shared constants + shared data file paths
├── data/                                   # generated by Step 00 (gitignored)
│   ├── training_data.csv
│   ├── training_baseline.csv
│   ├── production_stream.csv
│   ├── production_predictions.csv
│   └── model.joblib
├── 00_generate_data/
│   ├── 00_generate_data.py                # the ONLY place data is generated / the model trained+scored
│   └── 00_generate_data.md
├── 01_drift_and_missing_values/
│   ├── 01_drift_and_missing_values.py      # loads Step 00's data, logs baseline + predictions to MPM
│   └── 01_drift_and_missing_values.md
├── 02_correlation_view/
│   ├── 02_correlation_view.py
│   └── 02_correlation_view.md
├── 03_alerting/
│   ├── 03_alerting.py
│   └── 03_alerting.md
├── 04_model_registry/
│   ├── 04_model_registry.py
│   └── 04_model_registry.md
└── 05_segmentation/
    ├── 05_segmentation.py
    └── 05_segmentation.md
```

## Known limitations (this environment)

- Comet MPM's backend rejects events older than ~90 days and rejects future-dated events — this
  demo's 30-day window is comfortably inside both bounds, but regenerate close to when you intend
  to log (`00_generate_data.py` always regenerates relative to "now").
- There is no SDK/REST call for creating MPM alert rules or Custom Metrics — Steps 02/03/05 are
  manual/documented for those specific actions (confirmed against `comet_ml.API` and the MPM REST
  endpoints doc), matching `pharma-demand-forecasting`'s own conclusion.
- Step 03's local EMD numbers are aggregated per period (pre-break / during-break / post-retrain),
  not per single day — at this demo's synthetic volume (40 events/day), single-day EMD against the
  full training baseline is dominated by sampling noise, not signal. Treat the printed numbers as
  directional confirmation, not a literal prediction of the live per-day chart.
- If you change the underlying data-generation logic (not just re-running
  `00_generate_data.py` with the same logic), delete the model in the Model Registry
  and re-log fresh rather than trying to patch a live model — see
  `MPM/pharma-demand-forecasting/README.md` ("Resetting between presentations") for the exact
  gotchas (duplicate `predictionId`s, the training-dataset name being a separate object from the
  model).
