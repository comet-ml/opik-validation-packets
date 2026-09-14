# Step 06 — Dashboard: UI Checklist

**Docs:** [Dashboards](https://www.comet.com/docs/opik/v1/production/dashboards/)

Run `python 06_dashboard/seed_historical_data.py`, then `python 06_dashboard/06_dashboard.py`, then
verify in Opik UI > Projects > `multi-agent-orchestration-poc` > Dashboards.

- [ ] A dashboard named `Multi-Agent Orchestration PoC — Online Eval Trend` appears, with 4 sections
- [ ] **Volume & Cost**: trace count + total cost stats cards, plus trend lines, both including the 12 backdated points from `seed_historical_data.py`
- [ ] **Latency**: span duration (p50) by name shows separate series for `invoke_agent triage_agent`/`invoke_agent forecast_agent`/etc., `execute_tool <name>`, and `chat gpt-4o-mini`
- [ ] **Orchestration Quality**: `orchestration_correctness` AND `rag_groundedness` both show a dip around ~8 days ago and a recovery by the most recent points (two distinct lines, different trough position/depth)
- [ ] **Token Usage**: total tokens by node shows the `chat gpt-4o-mini` series
- [ ] Re-running `06_dashboard.py` does NOT duplicate sections/widgets (idempotent — see `dash.replace_sections([])` at the top of `build()`)

This is the last step. See `README.md` for the full packet summary.
