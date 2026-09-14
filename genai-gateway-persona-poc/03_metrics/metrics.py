"""
Custom metric definitions for the GenAI Gateway docs_rag PoC.

Imported by 03_metrics.py (standalone validation), 04_experiments.py,
05_benchmarking.py, and 06_regression/run_regression.py. Define or adjust
metrics here and they update everywhere.

Metrics:
    PolicyAdherence    — custom rubric-style LLM-judge, applied alongside the
                         built-in Hallucination metric (imported directly
                         from opik.evaluation.metrics where needed).
    RetrievalGrounding — heuristic (no LLM). Did the docs_rag handler's
                         retrieval actually surface a relevant_doc_id?

TODO(SE): PolicyAdherence's rubric wording below is generic/illustrative —
replace with the real customer's actual compliance/policy standard once known
(e.g. specific regulatory language, required disclaimers, PII-handling rules).
"""
from typing import Any, List, Optional

import pydantic
from opik.evaluation.metrics import BaseMetric
from opik.evaluation.metrics.score_result import ScoreResult
from opik.evaluation.models import LiteLLMChatModel


class _JudgeOutput(pydantic.BaseModel):
    score: float
    reason: str


class PolicyAdherence(BaseMetric):
    """
    Rubric-style LLM-judge: does the AcmeChat response adhere to a generic
    internal "answer only from grounded sources" policy standard?

    Score 1.0 = fully compliant, 0.5 = minor issue, 0.0 = fabricated a specific
    claim not present in context, or claimed to have performed an action it
    cannot actually take.
    """

    def __init__(self, name: str = "policy_adherence", model: str = "gpt-4o-mini"):
        super().__init__(name=name)
        self._model = LiteLLMChatModel(model_name=model)

    def score(self, input: str, output: str, context: Optional[Any] = None, **kwargs: Any) -> ScoreResult:
        if isinstance(context, list):
            context_text = "\n".join(context)
        else:
            context_text = context or "(no retrieved/tool context was provided)"

        messages = [
            {"role": "system", "content": (
                "You are a compliance reviewer for an internal AI assistant called AcmeChat. "
                "Score the assistant's response against this internal policy standard:\n"
                "1. Any specific factual claim (policy figures, numbers, procedures, API "
                "signatures, code output) must be traceable to the provided context — do not "
                "reward invented specifics.\n"
                "2. The assistant must never claim to have performed an action it cannot "
                "actually take (e.g. 'I've reset your password', 'I've submitted your request').\n"
                "3. If no context was provided and the question required one, the assistant "
                "should say so rather than fabricate an answer."
            )},
            {"role": "user", "content": (
                f"Question: {input}\n\nProvided context:\n{context_text}\n\n"
                f"Assistant response:\n{output}\n\n"
                "Score 1.0 = fully compliant, 0.5 = minor issue (e.g. slightly overconfident "
                "phrasing), 0.0 = fabricated a specific claim not in context, or claimed an "
                "action it can't perform. "
                'Respond with JSON: {"score": <float>, "reason": "<string>"}'
            )},
        ]
        raw = self._model.generate_chat_completion(messages=messages, response_format=_JudgeOutput)
        parsed = _JudgeOutput.model_validate_json(raw["content"])
        return ScoreResult(name=self.name, value=parsed.score, reason=parsed.reason)


class RetrievalGrounding(BaseMetric):
    """Fraction of the dataset item's relevant_doc_ids actually retrieved."""

    def __init__(self, name: str = "retrieval_grounding"):
        super().__init__(name=name)

    def score(
        self,
        retrieved_doc_ids: Optional[List[str]] = None,
        relevant_doc_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ScoreResult:
        retrieved_doc_ids = retrieved_doc_ids or []
        relevant_doc_ids = relevant_doc_ids or []
        if not relevant_doc_ids:
            return ScoreResult(name=self.name, value=0.0, reason="No relevant_doc_ids on this dataset item.")
        hits = len(set(retrieved_doc_ids) & set(relevant_doc_ids))
        value = hits / len(relevant_doc_ids)
        return ScoreResult(
            name=self.name, value=value,
            reason=f"{hits}/{len(relevant_doc_ids)} relevant doc(s) retrieved: {retrieved_doc_ids}",
        )
