"""
Loads synthetic demand-forecasting domain data used by agents.py.

Fully offline — no network calls, no real ML forecasting model. Each record
is one SKU's current inventory + a canned forecast + a canned anomaly flag.
The schema is intentionally similar in shape to what a real demand-
forecasting ML model would output (forecast_next_period, forecast_trend) so
this PoC's narrative lines up with a customer's actual forecasting
pipeline — but the two are NOT wired together; this is independent
synthetic data, not the output of any real or mocked ML model.

Also loads INCIDENT_REPORTS — a small synthetic document corpus for
anomaly_agent's real RAG tool (search_incident_reports in agents.py). This is
the one part of the packet with actual retrieval (keyword-overlap, same
technique as genai-gateway-persona-poc's tools.py), which is what gives
Step 02's rag-groundedness online eval rule real retrieved context to score.

TODO(SE): once the real customer's forecasting/inventory data schema and
real incident-report source are known, replace these JSON files (and the
field names agents.py reads) with the real integrations.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str):
    with open(DATA_DIR / name) as f:
        return json.load(f)


# list[{sku, region, current_stock, reorder_point, forecast_next_period,
#       forecast_trend, anomaly: {detected, description}}]
DEMAND_RECORDS = _load("domain_data.json")

# list[{id, sku, title, content}]
INCIDENT_REPORTS = _load("incident_reports.json")
