"""
Gateway/ingress layer for AcmeChat — this is the mock "app" that every
numbered step script calls.

Simulates a shared APIM/ingress layer in front of the AcmeChat docs_rag
handler: every request passes through a mock routing-decision log here
BEFORE dispatching to the handler (router.py). This is plain custom Python
— no agent framework — so every layer is just a directly-called,
`@opik.track`-decorated function. All of it lands in the same Opik trace,
as sibling spans under the outer gateway span:

    gateway_ingress                 <- this module, @opik.track span
      docs_rag                      <- router.py, the docs_rag handler
        search_internal_docs         <- tools.py, tool span (called on every query)
        chat_completion_create |
        anthropic_messages_create   <- automatic leaf span from
                                        track_openai/track_anthropic (tokens/cost)

Each function below is independently `@opik.track`-decorated and called
directly (no callback object) — that's what makes them nest under whichever
span is currently active, with no manual span wiring needed.

TODO(SE): replace the routing-decision logic below with the real customer's
APIM/ingress behavior once known (e.g. Azure APIM policy, Kong plugin,
custom gateway service) — including whatever real quota/rate-limiting they
actually enforce, which this PoC doesn't simulate.
"""
import os
import uuid
from typing import Optional

from dotenv import load_dotenv
import opik
from opik import opik_context

from router import run_docs_rag

load_dotenv()
os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")  # SDK only reads OPIK_API_KEY

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "genai-gateway-persona-poc")

# TODO(SE): confirm this matches the real customer's actual routing code
# structure once known — see router.py's own TODO(SE) for the full context.
ORCHESTRATION_FRAMEWORK = "custom"


@opik.track(name="gateway_ingress", project_name=OPIK_PROJECT_NAME)
def handle_request(
    query: str,
    *,
    thread_id: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Public entrypoint used by every step script — one call in, one Opik trace
    out (gateway span + nested docs_rag span).

    Args:
        query: the raw user message.
        thread_id: optional conversation thread id; generated if omitted.
        model: optional model override (defaults to router.py's hardcoded default).
    """
    thread_id = thread_id or str(uuid.uuid4())

    opik_context.update_current_span(
        metadata={"gateway.routing_target": "acmechat-agent-service-v1"},
        tags=["gateway", "ingress"],
    )
    opik_context.update_current_trace(
        thread_id=thread_id,
        tags=["gateway", ORCHESTRATION_FRAMEWORK],
        metadata={"orchestration_framework": ORCHESTRATION_FRAMEWORK},
    )

    result = run_docs_rag(query, model)

    trace_data = opik_context.get_current_trace_data()
    return {
        "response": result.get("response", ""),
        "tool_used": result.get("tool_used"),
        "context": result.get("context"),
        "retrieved_doc_ids": result.get("retrieved_doc_ids") or [],
        "trace_id": trace_data.id if trace_data else None,
        "thread_id": thread_id,
    }


def flush() -> None:
    """Flush the Opik message queue — call at the end of any standalone script."""
    opik.Opik().flush()
