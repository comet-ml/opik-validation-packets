"""
Real Microsoft Agent Framework -> Opik tracing bridge.

Microsoft Agent Framework has no native Opik SDK integration — but it DOES
ship its own real OpenTelemetry auto-instrumentation
(`agent_framework.observability`), which emits GenAI-semantic-convention
spans for every `Agent.run()` call, the underlying chat completion, and each
tool execution, with ZERO manual span-wrapping needed in agents.py or
orchestrator.py (verified live: one `Agent.run()` call with one tool
produces `invoke_agent -> chat -> execute_tool -> chat` automatically).

This module points that instrumentation's OTLP exporter at Opik and layers
`OpikSpanProcessor` on top so those spans thread onto the Opik-native trace
opened by the single `@opik.track` boundary (orchestrator.py's
`run_forecast_query`) — same in-process bridging mechanism as any other
OTel-instrumented library nested inside a tracked function.

Docs: https://www.comet.com/docs/opik/v1/tracing/integrations/opentelemetry/
      (see "Linking OpenTelemetry spans to an existing Opik trace")

TODO(SE): once the real Microsoft Agent Framework deployment is known, only
the OTLP endpoint/headers below change — the setup call itself is exactly
what a real deployment would use too.
"""
import os

from dotenv import load_dotenv
import agent_framework.observability as af_observability
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opik.integrations.otel import OpikSpanProcessor

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_WORKSPACE = os.getenv("OPIK_WORKSPACE", "default")
OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")

# Opik's OTLP ingest endpoint lives under the same API base the SDK itself
# uses — derive it from OPIK_URL_OVERRIDE (self-hosted/single-tenant) if set,
# otherwise the standard cloud API base.
_api_base = os.getenv("OPIK_URL_OVERRIDE") or "https://www.comet.com/opik/api"

# Built manually (not via configure_otel_providers's own otlp_endpoint= param)
# and passed through `exporters=` instead: that param routes through the
# framework's env-based helper, which unconditionally creates a metric AND a
# log exporter alongside the span exporter — but Opik's OTLP ingest only
# implements the traces endpoint, so those other two just spam
# "Failed to export {logs,metrics} batch: 404" on every flush. Passing
# a single pre-built OTLPSpanExporter here creates only what Opik supports.
_span_exporter = OTLPSpanExporter(
    endpoint=f"{_api_base}/v1/private/otel/v1/traces",
    headers={
        "Authorization": os.environ["OPIK_API_KEY"],
        "Comet-Workspace": OPIK_WORKSPACE,
        "projectName": OPIK_PROJECT_NAME,
    },
)
af_observability.configure_otel_providers(service_name=OPIK_PROJECT_NAME, exporters=[_span_exporter])
af_observability.enable_instrumentation(enable_sensitive_data=True)  # capture real prompt/tool-call content

trace.get_tracer_provider().add_span_processor(OpikSpanProcessor())


def flush_otel() -> None:
    """Force-export any buffered OTel spans — call at the end of any standalone script."""
    trace.get_tracer_provider().force_flush()
