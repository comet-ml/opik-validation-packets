"""
Step 06b — Dashboard

Builds a project-scoped Opik dashboard via the SDK's `opik.dashboard` object
API (see `opik.api_objects.dashboard` in the SDK for the full model).

Sections:
    Volume & Cost           — trace count + cost trend (also stats cards)
    Latency                 — span duration (p50) broken down by node name
    Orchestration Quality   — the orchestration_correctness dip-and-recovery
                              trend from Step 02's online eval rule, seeded
                              historically by seed_historical_data.py
    Token Usage             — span token usage broken down by node name

Run `seed_historical_data.py` first so the Orchestration Quality / Volume &
Cost charts have a real dip-and-recovery to show, not just today's
live-testing traffic from Steps 01-05.

Docs: https://www.comet.com/docs/opik/v1/production/dashboards/ (SDK section)

Usage:
    python 06_dashboard/06_dashboard.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import opik
from opik import dashboard

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY
OPIK_WORKSPACE = os.getenv("OPIK_WORKSPACE", "default")

# UI base URL: derive from OPIK_URL_OVERRIDE (self-hosted/single-tenant instances)
# if set, stripping the API path suffix; otherwise the standard cloud UI base.
_api_override = os.getenv("OPIK_URL_OVERRIDE")
OPIK_UI_BASE = _api_override.rsplit("/api", 1)[0] if _api_override else "https://www.comet.com/opik"

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")
DASHBOARD_NAME = "Multi-Agent Orchestration PoC — Online Eval Trend"


def get_or_create_dashboard(client: opik.Opik) -> dashboard.Dashboard:
    for existing in client.get_dashboards(name=DASHBOARD_NAME, max_results=10):
        if existing.name == DASHBOARD_NAME:
            print(f"Found existing dashboard {DASHBOARD_NAME!r} ({existing.id}) — reusing it.")
            return existing
    print(f"Creating dashboard {DASHBOARD_NAME!r}...")
    return client.create_dashboard(
        name=DASHBOARD_NAME,
        type=dashboard.DashboardType.MULTI_PROJECT,
        description=(
            "Demand-forecasting multi-agent orchestrator PoC — volume/cost, latency, and the "
            "Step 02 online-eval orchestration_correctness trend."
        ),
        project_name=OPIK_PROJECT_NAME,
    )


def build(dash: dashboard.Dashboard) -> None:
    # Clear any sections left over from a prior run of this script — add_section()
    # always appends, so re-running against a reused dashboard would otherwise
    # accumulate duplicate sections/widgets on every invocation.
    dash.replace_sections([])

    sections = {
        title: dash.add_section(title)
        for title in ("Volume & Cost", "Latency", "Orchestration Quality", "Token Usage")
    }

    # --- Volume & Cost -----------------------------------------------------
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_STATS_CARD,
            title="Total traces",
            config=dashboard.ProjectStatsCardConfig(metric=dashboard.StatsCardMetric.TRACE_COUNT),
        ),
        section_id=sections["Volume & Cost"],
    )
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_STATS_CARD,
            title="Total estimated cost",
            config=dashboard.ProjectStatsCardConfig(metric=dashboard.StatsCardMetric.TOTAL_ESTIMATED_COST_SUM),
        ),
        section_id=sections["Volume & Cost"],
    )
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_METRICS,
            title="Trace volume over time",
            config=dashboard.ProjectMetricsConfig(
                metric_type=dashboard.ProjectMetricType.TRACE_COUNT,
                chart_type=dashboard.ChartType.LINE,
            ),
        ),
        section_id=sections["Volume & Cost"],
    )
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_METRICS,
            title="Cost over time",
            config=dashboard.ProjectMetricsConfig(
                metric_type=dashboard.ProjectMetricType.COST,
                chart_type=dashboard.ChartType.LINE,
            ),
        ),
        section_id=sections["Volume & Cost"],
    )

    # --- Latency -------------------------------------------------------------
    # breakdown by span name (no span_filters — see repo convention: filters
    # remove the leaf spans where duration/token data actually lives).
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_METRICS,
            title="Span duration (p50) by name",
            config=dashboard.ProjectMetricsConfig(
                metric_type=dashboard.ProjectMetricType.SPAN_DURATION,
                chart_type=dashboard.ChartType.LINE,
                breakdown=dashboard.BreakdownConfig(field=dashboard.BreakdownField.NAME, sub_metric="p50"),
            ),
        ),
        section_id=sections["Latency"],
    )

    # --- Orchestration Quality -----------------------------------------------
    # This is the dip-and-recovery arc from seed_historical_data.py, standing
    # in for Step 02's two online eval rules scoring live traffic over time.
    # orchestration_correctness scores every trace; rag_groundedness only
    # scores anomaly-tagged ones (the specialist with a real RAG tool) — both
    # still plot fine on one chart since Opik just skips a series wherever a
    # trace has no value for it.
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_METRICS,
            title="orchestration_correctness / rag_groundedness over time",
            config=dashboard.ProjectMetricsConfig(
                metric_type=dashboard.ProjectMetricType.FEEDBACK_SCORES,
                chart_type=dashboard.ChartType.LINE,
                feedback_scores=["orchestration_correctness", "rag_groundedness"],
            ),
        ),
        section_id=sections["Orchestration Quality"],
    )

    # --- Token Usage ---------------------------------------------------------
    # subMetric required for SPAN_TOKEN_USAGE breakdown — see repo convention.
    dash.add_widget(
        dashboard.DashboardWidget(
            type=dashboard.WidgetType.PROJECT_METRICS,
            title="Total tokens by node",
            config=dashboard.ProjectMetricsConfig(
                metric_type=dashboard.ProjectMetricType.SPAN_TOKEN_USAGE,
                chart_type=dashboard.ChartType.LINE,
                breakdown=dashboard.BreakdownConfig(field=dashboard.BreakdownField.NAME, sub_metric="total_tokens"),
            ),
        ),
        section_id=sections["Token Usage"],
    )


def main():
    client = opik.Opik()

    dash = get_or_create_dashboard(client)
    build(dash)

    print(f"\nDashboard ready: {len(dash.sections)} section(s), "
          f"{sum(len(s.widgets) for s in dash.sections)} widget(s).")
    print(f"{OPIK_UI_BASE}/{OPIK_WORKSPACE}/dashboards/{dash.id}")
    print("\nSee 06_dashboard.md for the UI checklist.")


if __name__ == "__main__":
    main()
