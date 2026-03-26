from typing import Any, Literal
from typing_extensions import TypedDict


class PlannerGraphState(TypedDict, total=False):
    raw_json: dict[str, Any]
    filtered_json: dict[str, Any]
    cleaned_json: dict[str, Any]
    reusable_components: dict[str, Any]

    planner_payload: dict[str, Any]
    planner_summary: dict[str, Any]
    planner_chunks: list[dict[str, Any]]

    planner_payload_chars: int
    planner_payload_estimated_tokens: int
    chunk_count: int

    chunk_strategy: Literal[
        "single_call",
        "chunk_by_canvas_or_frame",
        "large_model_required",
    ]
    large_model_required: bool

    logs: list[str]