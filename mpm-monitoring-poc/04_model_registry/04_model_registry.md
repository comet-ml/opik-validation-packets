# Step 04 — Model Registry / Version History: UI Checklist

**Success criterion:** Retrain history correlated with issue timing. **Success:** version history
shows retrain events aligned with a known issue. **Test:** register model versions across
retrains; confirm timeline correlation is possible.

**Docs:** [Using Model Registry](https://www.comet.com/docs/v2/guides/model-registry/using-model-registry/) /
[MPM UI — models have a corresponding Model Registry entry](https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/#models-page)

**Prerequisite:** `python 00_generate_data/00_generate_data.py` (produces `data/model.joblib`).

## Run it

```bash
python 04_model_registry/04_model_registry.py --dry-run   # no credentials needed
python 04_model_registry/04_model_registry.py             # registers both versions with Comet
```

- [ ] `--dry-run` prints both version comments, referencing the same `BREAK_DAY`/`RETRAIN_DAY`
  numbers used throughout Steps 01–03
- [ ] Live run prints "Registered ... v1.0.0" then "Registered ... v1.1.0", then the registry's
  version list

## Verify in the UI

Open the Comet workspace's **Model Registry** (or the MPM model's page — both point at the same
registered model, since the registry name matches `MPM_MODEL_NAME`).

- [ ] Registry model `demand-forecast-poc` shows two versions: `1.0.0` and `1.1.0`
- [ ] `1.1.0`'s comment references the drift alert / retrain; `1.0.0`'s references the original
  deployment
- [ ] `1.1.0` is tagged/staged `production`, `1.0.0` is `archived`
- [ ] Cross-reference: filtering the MPM **Model Performance** page to `model_version = 1.0.0`
  shows the break; filtering to `1.1.0` shows recovery (same two version strings in both systems)
- [ ] Someone unfamiliar with this demo could look at the registry's version history next to the
  MPM drift chart and correctly answer "did we retrain around when this started, and did it
  help" — yes, and yes

Proceed to `05_segmentation/05_segmentation.py`.
