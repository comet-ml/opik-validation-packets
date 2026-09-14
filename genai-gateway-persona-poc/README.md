# GenAI Gateway Persona PoC — Opik Validation Scripts

Validation scripts for a generic "GenAI gateway" use case: a fictional company (**Acme Corp**)
fronting a fictional internal-documentation assistant (**AcmeChat**) with a shared ingress/APIM
("gateway") layer in front of a custom-code docs_rag handler (plain Python dispatch — no agent
framework). Work through the numbered steps in order — each step consumes artifacts produced by
the previous ones (seeded dataset, baseline experiment, etc.) rather than being disconnected
scripts.

Everything is offline/dev-scoped against synthetic data. No live/online evaluation, no
data-masking, no drift alerting, no real production traffic — see each step's docstring for the
`# TODO(SE):` markers showing exactly where a real solutions engineer would swap in the real
customer's specifics.

This packet is scoped to a single persona — **docs_rag** — chosen because it has the richest
metric story (Hallucination + PolicyAdherence + the docs_rag-specific RetrievalGrounding metric),
its tool call (`search_internal_docs`) fires unconditionally on every query, and it's the closest
match to a real customer's actual concern: hallucination caught via document grounding.

## The app

| Persona | Tool | Retrieval / grounding |
|---|---|---|
| `docs_rag` | `search_internal_docs` | always — keyword-overlap "RAG" over `data/knowledge_base.json` |

`router.py` is plain Python — **no agent framework** (no LangGraph, no Semantic Kernel, no
Microsoft Agent Framework): `gateway.py` dispatches directly to `router.run_docs_rag`. The handler
calls its tool and then generates the final answer with a **real OpenAI or Anthropic SDK call**
(`gpt-4o-mini` by default) — see `llm_clients.py` for the direct-SDK provider dispatch (no
LiteLLM) — so traces show genuine token/cost/latency data. `gateway.py` wraps every call in an
outer "gateway" span (mock routing decision); the docs_rag handler is an independently
`@opik.track`-decorated function called directly from `handle_request`, so every resulting Opik
trace has two visible layers: `gateway_ingress`, then the nested tool/LLM spans underneath.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in COMET_API_KEY / OPIK_WORKSPACE / an LLM key in .env
```

`.env` holds secrets only (Opik + LLM API keys/workspace). Everything else project-specific — the
project name, the persona's prompt and default model, dataset name, etc. — is hardcoded as plain
constants directly in whichever file uses it (no shared config module). There's no shared setup
module either — each entrypoint script starts with the same two lines: `load_dotenv()`, then
`os.environ["OPIK_API_KEY"] = os.getenv("COMET_API_KEY")`, since the SDK only ever reads
`OPIK_API_KEY` but the shared credentials file stores the key under `COMET_API_KEY`.

## Running

| Step | Script(s) | Checklist |
|------|-----------|-----------|
| 01 | `01_tracing/01_tracing.py` — exercise docs_rag, confirm gateway+handler nested traces | `01_tracing/01_tracing.md` |
| 02 | `02_datasets/02_datasets.py` — seed the docs_rag dataset, prove version history (update + insert) | `02_datasets/02_datasets.md` |
| 03 | `03_metrics/03_metrics.py` — validate Hallucination (built-in) + PolicyAdherence (custom) against canned good/bad samples, plus RetrievalGrounding | `03_metrics/03_metrics.md` |
| 04 | `04_experiments/04_experiments.py` — one `opik.evaluate()` against the docs_rag dataset | `04_experiments/04_experiments.md` |
| 05 | `05_benchmarking/05_benchmarking.py` — re-run docs_rag across 2 model variants | `05_benchmarking/05_benchmarking.md` |
| 06 | `06_regression/run_regression.py` (`--gate` to fail on regression), `simulate_config_regression.py`, `schedule_example.py` (reference only) | `06_regression/06_regression.md` |
| 07 | `07_annotation_queue/07_annotation_queue.py` — route flagged items into a review queue | `07_annotation_queue/07_annotation_queue.md` |
| 08 | `08_dashboard/seed_historical_data.py` then `08_dashboard/08_dashboard.py` | `08_dashboard/08_dashboard.md` |

Each step also has real UI checklists in its `.md` file. Set `NONINTERACTIVE=1` to skip the
`input()` UI-checkpoint pauses in Step 02 (used for automated/CI runs of this packet).

## Before running with a real customer

Search this repo for `# TODO(SE):` — every one marks a spot with a real prompt / real retriever /
real golden-set content / real compliance wording / a config value to swap in once the real
customer's specifics are known (start with `router.py` for the persona's prompt and model, and
`gateway.py` for the mock gateway's routing logic).

## Dataset

One Opik dataset, schema-matched to what "correct" means for docs_rag:

- `genai-gateway-docs-rag-qa` — `query`, `expected_output`, `relevant_doc_ids`

## Metrics

- **Hallucination** (built-in Opik metric).
- **PolicyAdherence** (custom LLM-judge, `03_metrics/metrics.py`) — a generic, illustrative
  "answer only from grounded sources, never claim an action you can't take" rubric. TODO(SE):
  replace the rubric wording with the real customer's actual compliance standard.
- **RetrievalGrounding** (custom, heuristic) — did the handler's retrieval actually surface a
  relevant doc?

## Known limitations (this environment)

- Some Opik Cloud workspace tiers enforce a 24-hour ingestion window on backdated trace IDs. If
  `08_dashboard/seed_historical_data.py` fails with `reason 'too_old'`, lower `DAYS_BACK` in that
  file or check your workspace's historical-ingestion allowance.
- `track_openai`/`track_anthropic` stamp genuine token usage + cost directly onto their own LLM
  leaf span (`chat_completion_create` / `anthropic_messages_create`) — no manual stamping needed.
  Dashboard latency breakdowns are keyed on the `docs_rag` handler span name; token/cost breakdowns
  are keyed on the LLM leaf span names above.
