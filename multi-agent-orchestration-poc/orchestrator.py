"""
Real Microsoft Agent Framework orchestrator for the demand-forecasting
multi-agent PoC.

A real triage `Agent` (LLM-driven, not a keyword classifier) decides which of
the 3 specialist agents (agents.py) are relevant to a query, by calling
whichever `needs_*_agent` tool(s) apply. Calling more than one tool is how an
ambiguous, multi-domain query naturally fans out to more than one specialist
— mirroring the customer's stated "ambiguity" concern: does the orchestrator
correctly consult every relevant specialist rather than guessing one and
dropping the others. (Verified live: an early looser triage prompt
over-triggered — flagged all 3 domains on single-domain questions — tightened
to "most questions need exactly ONE tool call" + temperature=0, which routed
5/5 test queries correctly.)

Every `agent.run()` call (triage + each dispatched specialist + synthesis) is
real Microsoft Agent Framework code producing its own real OTel span tree
(`invoke_agent -> chat -> execute_tool -> chat` — see agents.py), bridged
into one merged Opik trace via `OpikSpanProcessor` (otel_setup.py) underneath
the single `@opik.track` boundary below (`run_forecast_query`).

Considered and rejected: `agent_framework_orchestrations.HandoffBuilder`
(the framework's own decentralized multi-agent routing builder). Live-tested
against real OpenAI — it required extra setup
(`require_per_service_call_history_persistence`, `.with_start_agent()`,
`.with_autonomous_mode()`) and, once running, looped 35+ turns without
converging to a single answer. Its conversational/autonomous-continuation
design targets open-ended chat, not a bounded single-answer-per-query flow,
so the simpler triage-then-dispatch pattern below was used instead.

TODO(SE): replace the triage instructions with the real customer's actual
Microsoft Agent Framework routing/planner logic once known.
"""
import os

import opik
from opik import opik_context
from agent_framework import Agent, ChatOptions, tool
from agent_framework.openai import OpenAIChatClient

import otel_setup  # noqa: F401  side-effecting: registers the OTel -> Opik bridge
import agents

OPIK_PROJECT_NAME = os.getenv("OPIK_PROJECT_NAME", "multi-agent-orchestration-poc")
ORCHESTRATION_FRAMEWORK = "microsoft_agent_framework"

_flagged_domains: set = set()


@tool
def needs_forecast_agent() -> str:
    """The question asks about future/projected demand, forecast trend, or expected volume."""
    _flagged_domains.add("forecast")
    return "noted"


@tool
def needs_inventory_agent() -> str:
    """The question asks about current stock on hand, warehouse quantity, or reorder status."""
    _flagged_domains.add("inventory")
    return "noted"


@tool
def needs_anomaly_agent() -> str:
    """The question asks WHY something unusual happened to demand (a spike, dip, or drop)."""
    _flagged_domains.add("anomaly")
    return "noted"


TRIAGE_INSTRUCTIONS = (  # TODO(SE): real routing logic once known
    "Classify a supply-chain question about a SKU by calling ONLY the needs_*_agent "
    "tool(s) that are directly relevant. Most questions only need exactly ONE tool call. "
    "Only call more than one tool if the question clearly asks about more than one topic "
    "in the same sentence (e.g. both stock AND forecast). Never call a tool for a topic "
    "the question does not mention at all."
)
_triage_client = OpenAIChatClient(model="gpt-4o-mini")  # TODO(SE): real model
triage_agent = Agent(
    _triage_client, name="triage_agent", instructions=TRIAGE_INSTRUCTIONS,
    tools=[needs_forecast_agent, needs_inventory_agent, needs_anomaly_agent],
    default_options=ChatOptions(temperature=0),
)

SPECIALIST_AGENTS = {
    "forecast": agents.forecast_agent,
    "inventory": agents.inventory_agent,
    "anomaly": agents.anomaly_agent,
}

SYNTHESIS_INSTRUCTIONS = (  # TODO(SE): real prompt
    "You are a supply-chain assistant. Using ONLY the specialist responses provided "
    "below, answer the user's question concisely. If more than one specialist responded, "
    "address all of them. Never invent a number or fact not present in the responses."
)
_synthesis_client = OpenAIChatClient(model="gpt-4o-mini")  # TODO(SE): real model
synthesis_agent = Agent(_synthesis_client, name="synthesis_agent", instructions=SYNTHESIS_INSTRUCTIONS)


async def classify_domains(query: str) -> list:
    """Real LLM-driven routing decision (via tool-calling), not a keyword classifier."""
    _flagged_domains.clear()
    await triage_agent.run(query)
    return sorted(_flagged_domains) or ["forecast"]


@opik.track(name="orchestrator_run", project_name=OPIK_PROJECT_NAME)
async def run_forecast_query(query: str, sku: str) -> dict:
    """
    Public entrypoint used by every step script — one call in, one merged
    Opik trace out (orchestrator_run span + one real invoke_agent subtree
    per agent actually run: triage, each dispatched specialist, synthesis).
    """
    agents._retrieved_context.clear()

    full_query = f"{query} (SKU: {sku})"
    domains = await classify_domains(full_query)

    # Per-domain tags let Step 02's rag-groundedness rule filter to only the
    # traces where anomaly_agent (the one specialist with a real RAG tool)
    # actually ran — set after classification since the domains aren't known
    # any earlier.
    opik_context.update_current_trace(
        tags=["orchestrator", ORCHESTRATION_FRAMEWORK, *domains],
        metadata={"orchestration_framework": ORCHESTRATION_FRAMEWORK},
    )

    specialist_responses = {}
    for domain in domains:
        result = await SPECIALIST_AGENTS[domain].run(full_query)
        specialist_responses[domain] = result.text

    synthesis_input = f"{query}\n\nSpecialist responses:\n" + "\n".join(
        f"- {domain}: {text}" for domain, text in specialist_responses.items()
    )
    final = await synthesis_agent.run(synthesis_input)

    trace_data = opik_context.get_current_trace_data()
    return {
        "response": final.text,
        "domains_routed": domains,
        "ambiguous": len(domains) > 1,
        "specialist_responses": specialist_responses,
        "retrieved_context": dict(agents._retrieved_context),
        "trace_id": trace_data.id if trace_data else None,
    }


def flush() -> None:
    """Flush the Opik message queue and any buffered OTel spans — call at the end of any standalone script."""
    opik.Opik().flush()
    otel_setup.flush_otel()
