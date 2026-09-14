# Step 01 — Tracing: UI Checklist

**Docs:** [OpenAI integration](https://www.comet.com/docs/opik/v1/tracing/integrations/openai/) /
[Anthropic integration](https://www.comet.com/docs/opik/v1/tracing/integrations/anthropic/)

Run `python 01_tracing/01_tracing.py`, then verify in Opik UI > Projects > `genai-gateway-persona-poc` > Traces.

- [ ] 3 new traces appear, one per sample query
- [ ] Each trace's top-level span is named `gateway_ingress`
- [ ] Expanding a trace shows a `docs_rag` span nested directly under `gateway_ingress`
- [ ] A `search_internal_docs` tool span appears nested under the `docs_rag` span on every trace (unconditional — it's called on every query)
- [ ] A `chat_completion_create` (OpenAI) leaf span appears under the `docs_rag` span with non-zero token usage
- [ ] Trace metadata shows `orchestration_framework: custom`

Proceed to `02_datasets/02_datasets.py`.
