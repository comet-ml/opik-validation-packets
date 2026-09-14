# Step 03 — Threshold-Based Alerting: UI Checklist

**Success criterion:** Alerts fire on tracked metrics crossing a threshold. **Success:** alert
fires correctly on a configured rule. **Test:** configure a threshold rule; confirm it fires.

**Docs:** [Alerts page](https://www.comet.com/docs/v2/guides/model-production-monitoring/mpm-ui/#alerts-page)

**Prerequisite:** `00_generate_data/00_generate_data.py` (local numbers only — no live logging
required for this step's script, though the alert rule itself is created against live data from
Step 01).

## Run it

```bash
python 03_alerting/03_alerting.py
```

- [ ] Prints `pre-break`, `during-break`, and `post-retrain` EMD for `warehouse_inventory_level`,
  with `during-break` clearly the largest of the three (directional sanity check only — see the
  script's module docstring for why day-by-day EMD at this demo's synthetic volume is too noisy
  to use as a literal per-day prediction)

## Create the alert rule (manual — no SDK/REST call exists for this)

1. Go to the model's **Alerts** page → **+ Add Alert Rule**.
2. Metric: **Input Drift (EMD)** on `warehouse_inventory_level`.
3. Threshold: pick a value between the live pre-break and during-break numbers you see in the
   **Features > warehouse_inventory_level > Drift** tab (Step 01) — the script's aggregated
   numbers tell you roughly how much separation to expect.
4. Optional filter: scope to a specific `region` to demonstrate a segment-specific alert (ties
   into Step 05).
5. If you also want an **accuracy-based** alert (on the `Accuracy (MAE)` custom metric from Step
   02), set its **evaluation delay** to `7 days` (`LABEL_DELAY_DAYS`) — otherwise it evaluates on
   incomplete data and can fire (or fail to fire) for the wrong reason.

## Verify in the UI

- [ ] The new rule appears on the **Alerts** page, enabled
- [ ] A notification/alert entry exists for the break window (days 23–26 in this run) once the
  rule has had a chance to evaluate
- [ ] (Optional) Temporarily lower the threshold to confirm the rule mechanism fires at all, then
  reset it to the value chosen above

Proceed to `04_model_registry/04_model_registry.py`.
