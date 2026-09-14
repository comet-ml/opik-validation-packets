# Step 08 — Dashboard: UI Checklist

**Docs:** [Dashboards](https://www.comet.com/docs/opik/v1/production/dashboards/)

1. Run `python 08_dashboard/seed_historical_data.py` (backdates ~12 points over 14 days — see the
   NOTE in that file if your workspace rejects backdating beyond 24h).
2. Run `python 08_dashboard/08_dashboard.py`.

In Opik UI > Dashboards > `GenAI Gateway Persona PoC — Regression Trend`:

- [ ] 4 sections exist: Volume & Cost, Latency, Quality Trend, Token Usage
- [ ] Volume & Cost: trace count + total cost stats cards render, plus trend-over-time line charts
- [ ] Latency: span duration (p50) by name shows a separate series for `docs_rag` (and its nested spans)
- [ ] Quality Trend: `policy_adherence` dips and `hallucination` rises around the middle of the 14-day window, both recovering toward the most recent days
- [ ] Token Usage: total tokens by name shows non-zero series for the LLM leaf spans (`chat_completion_create` / `anthropic_messages_create`) — these carry native token usage directly from `track_openai`/`track_anthropic`, no manual stamping

TODO(SE): once this is used in a live customer engagement, replace the fictional AcmeChat dip
narrative with a real regression window from the customer's own `06_regression` history.
