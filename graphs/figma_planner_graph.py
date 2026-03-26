import json
from typing import Any, Literal

from langgraph.graph import StateGraph, START, END

from config.settings import (
    RAW_OUTPUT_FILE,
    CLEANED_OUTPUT_FILE,
    COMPONENT_REU_OUTPUT_FILE,
    PLANNER_PAYLOAD_FILE,
    PLANNER_SUMMARY_FILE,
    PLANNER_CHUNKS_FILE,
    PLANNER_MAX_DEPTH,
    PLANNER_MAX_CHARS_SINGLE_CALL,
    PLANNER_MAX_CHARS_PER_CHUNK,
    PLANNER_MAX_CHUNKS,
)
from graphs.state import PlannerGraphState
from services.figma.fetcher import fetch_figma_file, save_raw
from services.figma.canvas_filter import filter_canvases
from services.figma.cleaner import clean_tree
from services.figma.component_reu import extract_reusable_components
from services.planner.payload_builder import build_planner_payload
from services.planner.size_estimator import estimate_json_size
from services.planner.summary_builder import build_global_summary
from services.planner.chunking import build_structural_chunks


def _append_log(state: PlannerGraphState, message: str) -> list[str]:
    logs = list(state.get("logs", []))
    logs.append(message)
    return logs


def _save_json(path, data: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_or_fetch_raw_node(state: PlannerGraphState) -> dict[str, Any]:
    if state.get("raw_json"):
        return {"logs": _append_log(state, "[graph] raw_json déjà présent dans le state.")}

    if RAW_OUTPUT_FILE.exists():
        with open(RAW_OUTPUT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {
            "raw_json": raw,
            "logs": _append_log(state, f"[graph] Raw chargé depuis disque -> {RAW_OUTPUT_FILE}"),
        }

    raw = fetch_figma_file()
    save_raw(raw)
    return {
        "raw_json": raw,
        "logs": _append_log(state, f"[graph] Raw récupéré via API et sauvegardé -> {RAW_OUTPUT_FILE}"),
    }


def filter_canvases_node(state: PlannerGraphState) -> dict[str, Any]:
    filtered = filter_canvases(state["raw_json"])
    return {
        "filtered_json": filtered,
        "logs": _append_log(state, "[graph] Canvases filtrés."),
    }


def clean_tree_node(state: PlannerGraphState) -> dict[str, Any]:
    cleaned = clean_tree(state["filtered_json"])
    _save_json(CLEANED_OUTPUT_FILE, cleaned)

    return {
        "cleaned_json": cleaned,
        "logs": _append_log(state, f"[graph] JSON nettoyé sauvegardé -> {CLEANED_OUTPUT_FILE}"),
    }


def extract_reusable_components_node(state: PlannerGraphState) -> dict[str, Any]:
    if COMPONENT_REU_OUTPUT_FILE.exists():
        with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
            reusable = json.load(f)
        return {
            "reusable_components": reusable,
            "logs": _append_log(state, f"[graph] reusable loaded -> {COMPONENT_REU_OUTPUT_FILE}"),
        }

    reusable = extract_reusable_components()
    return {
        "reusable_components": reusable,
        "logs": _append_log(state, f"[graph] reusable extracted -> {COMPONENT_REU_OUTPUT_FILE}"),
    }


def build_planner_payload_node(state: PlannerGraphState) -> dict[str, Any]:
    payload = build_planner_payload(
        cleaned_json=state["cleaned_json"],
        reusable_components_data=state["reusable_components"],
        max_depth=PLANNER_MAX_DEPTH,
    )
    _save_json(PLANNER_PAYLOAD_FILE, payload)

    return {
        "planner_payload": payload,
        "logs": _append_log(state, f"[graph] planner payload saved -> {PLANNER_PAYLOAD_FILE}"),
    }


def estimate_payload_size_node(state: PlannerGraphState) -> dict[str, Any]:
    size = estimate_json_size(state["planner_payload"])
    return {
        "planner_payload_chars": size["chars"],
        "planner_payload_estimated_tokens": size["estimated_tokens"],
        "logs": _append_log(
            state,
            f"[graph] payload size = {size['chars']} chars (~{size['estimated_tokens']} tokens)",
        ),
    }


def build_summary_node(state: PlannerGraphState) -> dict[str, Any]:
    summary = build_global_summary(state["planner_payload"])
    _save_json(PLANNER_SUMMARY_FILE, summary)

    return {
        "planner_summary": summary,
        "logs": _append_log(state, f"[graph] summary saved -> {PLANNER_SUMMARY_FILE}"),
    }


def choose_strategy_node(state: PlannerGraphState) -> dict[str, Any]:
    chars = state["planner_payload_chars"]

    if chars <= PLANNER_MAX_CHARS_SINGLE_CALL:
        return {
            "chunk_strategy": "single_call",
            "large_model_required": False,
            "logs": _append_log(state, "[graph] strategy = single_call"),
        }

    return {
        "chunk_strategy": "chunk_by_canvas_or_frame",
        "large_model_required": False,
        "logs": _append_log(state, "[graph] strategy = chunk_by_canvas_or_frame"),
    }


def choose_strategy_router(state: PlannerGraphState) -> Literal["single_call", "chunk_by_canvas_or_frame"]:
    return state["chunk_strategy"]


def build_chunks_node(state: PlannerGraphState) -> dict[str, Any]:
    chunks = build_structural_chunks(
        planner_payload=state["planner_payload"],
        global_summary=state["planner_summary"],
        max_chars_per_chunk=PLANNER_MAX_CHARS_PER_CHUNK,
    )

    chunk_count = len(chunks)
    _save_json(PLANNER_CHUNKS_FILE, chunks)

    if chunk_count > PLANNER_MAX_CHUNKS:
        return {
            "planner_chunks": chunks,
            "chunk_count": chunk_count,
            "chunk_strategy": "large_model_required",
            "large_model_required": True,
            "logs": _append_log(state, f"[graph] too many chunks ({chunk_count}) -> large_model_required"),
        }

    return {
        "planner_chunks": chunks,
        "chunk_count": chunk_count,
        "large_model_required": False,
        "logs": _append_log(state, f"[graph] chunks saved -> {PLANNER_CHUNKS_FILE}"),
    }


def build_figma_planner_graph():
    builder = StateGraph(PlannerGraphState)

    builder.add_node("load_or_fetch_raw", load_or_fetch_raw_node)
    builder.add_node("filter_canvases", filter_canvases_node)
    builder.add_node("clean_tree", clean_tree_node)
    builder.add_node("extract_reusable_components", extract_reusable_components_node)
    builder.add_node("build_planner_payload", build_planner_payload_node)
    builder.add_node("estimate_payload_size", estimate_payload_size_node)
    builder.add_node("build_summary", build_summary_node)
    builder.add_node("choose_strategy", choose_strategy_node)
    builder.add_node("build_chunks", build_chunks_node)

    builder.add_edge(START, "load_or_fetch_raw")
    builder.add_edge("load_or_fetch_raw", "filter_canvases")
    builder.add_edge("filter_canvases", "clean_tree")
    builder.add_edge("clean_tree", "extract_reusable_components")
    builder.add_edge("extract_reusable_components", "build_planner_payload")
    builder.add_edge("build_planner_payload", "estimate_payload_size")
    builder.add_edge("estimate_payload_size", "build_summary")
    builder.add_edge("build_summary", "choose_strategy")

    builder.add_conditional_edges(
        "choose_strategy",
        choose_strategy_router,
        {
            "single_call": END,
            "chunk_by_canvas_or_frame": "build_chunks",
        },
    )

    builder.add_edge("build_chunks", END)

    return builder.compile()


graph = build_figma_planner_graph()