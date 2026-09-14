"""
Feedback-definition taxonomy for the GenAI Gateway regression review queue.

Adapted from field-service-csr-agent's qa_rubric.py pattern: define the
feedback definitions once (`ensure_taxonomy`), create the traces annotation
queue once, then route flagged items into it from other scripts.

TODO(SE): swap `ROOT_CAUSE_CATEGORIES` for the real customer's actual triage
taxonomy once known (their categories will reflect their own tool/persona set).
"""
import opik
from opik.rest_api.core.api_error import ApiError
from opik.rest_api.types.categorical_feedback_detail_create import CategoricalFeedbackDetailCreate
from opik.rest_api.types.feedback_create import FeedbackCreate_Categorical, FeedbackCreate_Numerical
from opik.rest_api.types.numerical_feedback_detail_create import NumericalFeedbackDetailCreate

QUEUE_NAME = "GenAI Gateway Regression Review"
QUEUE_INSTRUCTIONS = (
    "Review this flagged interaction. Confirm whether the response was actually a quality "
    "regression, tag the most likely root cause, and rate how severe it is."
)

ROOT_CAUSE_CATEGORIES = {
    "prompt_regression": 1.0,
    "retrieval_miss": 2.0,
    "hallucination": 3.0,
    "other": 4.0,
}

FEEDBACK_DEFINITIONS = [
    FeedbackCreate_Categorical(
        name="root_cause",
        description="Most likely root cause of the flagged interaction's quality issue.",
        details=CategoricalFeedbackDetailCreate(categories=ROOT_CAUSE_CATEGORIES),
    ),
    FeedbackCreate_Numerical(
        name="severity",
        description="How severe is this issue in practice? 1 (cosmetic) - 5 (would upset a real user).",
        details=NumericalFeedbackDetailCreate(min=1, max=5),
    ),
]


def ensure_taxonomy(client: opik.Opik, project_name: str):
    """Create the feedback definitions + traces annotation queue if missing (idempotent)."""
    for definition in FEEDBACK_DEFINITIONS:
        try:
            client.rest_client.feedback_definitions.create_feedback_definition(request=definition)
        except ApiError as e:
            if e.status_code != 409:
                raise

    for queue in client.get_traces_annotation_queues(project_name=project_name):
        if queue.name == QUEUE_NAME:
            return queue
    return client.create_traces_annotation_queue(
        name=QUEUE_NAME,
        project_name=project_name,
        description="Individual interactions flagged by the Step 06 regression gate.",
        instructions=QUEUE_INSTRUCTIONS,
        comments_enabled=True,
        feedback_definition_names=[d.name for d in FEEDBACK_DEFINITIONS],
    )
