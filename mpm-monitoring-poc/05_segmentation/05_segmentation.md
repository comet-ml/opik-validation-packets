# Step 05 — Custom Metric Segmentation: UI Checklist

**Success criterion:** Narrow down where a degradation is occurring by filtering/segmenting on
any explicitly logged feature (e.g. business unit). **Success:** metrics segmentable by ≥1 logged
dimension. **Test:** log business unit as a custom field; confirm metric is filterable/segmentable
by it.

**Docs:** [Custom metrics — subset of predictions](https://www.comet.com/docs/v2/guides/model-production-monitoring/custom-metrics/#custom-metrics-for-a-subset-of-predictions)

**Prerequisite:** `00_generate_data/00_generate_data.py` and `01_drift_and_missing_values.py` (live,
not `--dry-run`) must have already run.

## Run it

```bash
python 05_segmentation/05_segmentation.py
```

- [ ] Prints a locally reconstructed MAE-by-region table (labeled events only) — confirms the
  segments aren't identical, i.e. there's something real to filter down to

## Example segmented custom-metric SQL

A `WHERE` predicate on any `feature_<name>` column — same dialect as Step 02, just narrowed to
one segment. Repeat per region, or use the UI's region filter control instead of one metric per
value (see "Verify in the UI" below).

```sql
SELECT MAE("prediction_predicted_units", "label_value_actual_units")
FROM MODEL WHERE "feature_region" = 'Northeast'
```

## Verify in the UI

- [ ] On the **Model Performance** page, use the region **filter** (not a new custom metric) to
  switch between 2–3 regions and confirm Accuracy/Distribution/Drift all update to that region's
  data only
- [ ] (Optional) Add the SQL above (or repeat it for another region) as a custom metric in
  Settings and confirm it appears next to the plain `Accuracy (MAE)` metric from Step 02
- [ ] Confirm the break from Step 01 shows up in every region, not just one — this is what
  distinguishes "systemic, upstream-feed issue" from "problem local to one part of the business,"
  which segmentation is what lets you tell apart
- [ ] Any other logged feature (`product_category` in this dataset) is filterable/segmentable the
  same way — segmentation isn't special-cased to `region`

This is the last step. See `README.md` for the full packet summary and how each of the 5 success
criteria maps back to Steps 01–05.
