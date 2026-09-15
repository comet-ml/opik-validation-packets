"""
Real OpenTelemetry SDK -> Opik tracing bridge for the GitHub Copilot Chat
Spec-Kit harness.

GitHub Copilot Chat is closed-source, so there's no framework to
auto-instrument. Instead, copilot_session.py builds the OTel span tree by
hand, directly against the raw opentelemetry-sdk tracer API, in the exact
documented schema GitHub ships for enterprise-managed Copilot Chat OTel
export (``invoke_agent -> chat / execute_tool / execute_hook``). Once a real
customer points their actual managed OTLP endpoint at Opik, the Opik-side
setup below (an exporter on a plain ``TracerProvider``) is exactly what
they'd reuse — only the endpoint/headers change.

This module builds nothing beyond a plain ``TracerProvider`` plus a
hand-built ``OTLPSpanExporter`` pointed at Opik's OTLP endpoint, and exposes
a shared ``TRACER``. There is no Opik SDK object anywhere in this file — this
whole harness is 100% raw OTLP, the same as a real GitHub-managed Copilot
deployment would be.

GOTCHA: Opik's OTLP ingest endpoint only implements the traces endpoint, not
metrics or logs. That's why this whole packet represents things like token
totals and accept/reject/feedback signals as span attributes
(``gen_ai.usage.*``, ``github.copilot.edit.accepted``,
``github.copilot.feedback.vote``) rather than OTel metric instruments. See
copilot_session.py's module docstring for the full picture.

Once the real customer's GitHub Enterprise-managed OTel export
endpoint/headers are known, only the exporter target below changes.
"""
import os

from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_WORKSPACE = os.getenv("OPIK_WORKSPACE", "default")
OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "agentic-sdlc")

# Opik's OTLP ingest endpoint lives under the same API base the SDK itself
# uses — derive it from OPIK_URL_OVERRIDE (self-hosted/single-tenant) if set,
# otherwise the standard cloud API base.
_api_base = os.getenv("OPIK_URL_OVERRIDE") or "https://www.comet.com/opik/api"

# Built manually and registered on a plain TracerProvider — only a traces
# exporter is ever created (Opik's OTLP ingestion doesn't support metrics or
# logs anyway, see module docstring).
_span_exporter = OTLPSpanExporter(
    endpoint=f"{_api_base}/v1/private/otel/v1/traces",
    headers={
        "Authorization": os.environ["OPIK_API_KEY"],
        "Comet-Workspace": OPIK_WORKSPACE,
        "projectName": OPIK_PROJECT_NAME,
    },
)

# NOTE: Opik's OTel ingestion never reads OTel resource-level attributes —
# only span-level attributes are inspected. The `service.name` set below is
# purely local OTel hygiene; it's not visible to Opik in any form. See the
# README's "developer identity has no path into Opik" section for why this
# also rules out resource-attribute injection as a way to carry identity.
_provider = TracerProvider(resource=Resource.create({"service.name": OPIK_PROJECT_NAME}))
_provider.add_span_processor(BatchSpanProcessor(_span_exporter))
trace.set_tracer_provider(_provider)

TRACER = trace.get_tracer("github.copilot.chat")


def flush_otel() -> None:
    """Force-export any buffered OTel spans — call at the end of any standalone script."""
    trace.get_tracer_provider().force_flush()
