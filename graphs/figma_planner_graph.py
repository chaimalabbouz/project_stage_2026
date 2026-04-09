"""
figma_planner_graph.py
----------------------
Graph LangGraph principal du projet.
Orchestre toutes les étapes depuis la récupération Figma jusqu'à la validation du code.
"""

import json
from typing import Any, Literal
from pathlib import Path

from langgraph.graph import StateGraph, START, END

from config.settings import (
    RAW_OUTPUT_FILE,
    CLEANED_OUTPUT_FILE,
    COMPONENT_REU_OUTPUT_FILE,
    PLANNER_PAYLOAD_FILE,
    PLANNER_SUMMARY_FILE,
    PLANNER_CHUNKS_FILE,
    PLANNER_PLANNING_FILE,
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
from llm.planner import generate_planning


# Imports des nouvelles étapes
from services.figma.style_converter import style_converter_node
from services.figma.route_mapper import route_mapper_node 
from agents.generator.scaffolder import scaffold_project_node
from agents.codegen_agent.node import codegen_node
#from agents.validation_agent.node import validation_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append_log(state: PlannerGraphState, message: str) -> list[str]:
    logs = list(state.get("logs", []))
    logs.append(message)
    print(message)
    return logs


def _save_json(path, data: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Phase 1 : Récupération et nettoyage Figma
# ---------------------------------------------------------------------------

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
        "logs": _append_log(state, f"[graph] Raw récupéré via API -> {RAW_OUTPUT_FILE}"),
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
        "logs": _append_log(state, f"[graph] JSON nettoyé -> {CLEANED_OUTPUT_FILE}"),
    }


def extract_reusable_components_node(state: PlannerGraphState) -> dict[str, Any]:
    if COMPONENT_REU_OUTPUT_FILE.exists():
        with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
            reusable = json.load(f)
        return {
            "reusable_components": reusable,
            "logs": _append_log(state, f"[graph] reusable chargé -> {COMPONENT_REU_OUTPUT_FILE}"),
        }

    reusable = extract_reusable_components()
    return {
        "reusable_components": reusable,
        "logs": _append_log(state, f"[graph] reusable extrait -> {COMPONENT_REU_OUTPUT_FILE}"),
    }


# ---------------------------------------------------------------------------
# Phase 2 : Construction du payload et stratégie
# ---------------------------------------------------------------------------

def build_planner_payload_node(state: PlannerGraphState) -> dict[str, Any]:
    payload = build_planner_payload(
        cleaned_json=state["cleaned_json"],
        reusable_components_data=state["reusable_components"],
        max_depth=PLANNER_MAX_DEPTH,
    )
    _save_json(PLANNER_PAYLOAD_FILE, payload)
    return {
        "planner_payload": payload,
        "logs": _append_log(state, f"[graph] payload sauvegardé -> {PLANNER_PAYLOAD_FILE}"),
    }


def estimate_payload_size_node(state: PlannerGraphState) -> dict[str, Any]:
    size = estimate_json_size(state["planner_payload"])
    return {
        "planner_payload_chars": size["chars"],                                                    
        "planner_payload_estimated_tokens": size["estimated_tokens"],
        "logs": _append_log(
            state,
            f"[graph] taille payload = {size['chars']} chars (~{size['estimated_tokens']} tokens)",
        ),
    }


def build_summary_node(state: PlannerGraphState) -> dict[str, Any]:
    summary = build_global_summary(state["planner_payload"])
    _save_json(PLANNER_SUMMARY_FILE, summary)
    return {
        "planner_summary": summary,
        "logs": _append_log(state, f"[graph] summary sauvegardé -> {PLANNER_SUMMARY_FILE}"),
    }


def choose_strategy_node(state: PlannerGraphState) -> dict[str, Any]:
    chars = state["planner_payload_chars"]

    if chars <= PLANNER_MAX_CHARS_SINGLE_CALL:
        return {
            "chunk_strategy": "single_call",
            "large_model_required": False,
            "logs": _append_log(state, f"[graph] stratégie = single_call ({chars} chars)"),
        }

    return {
        "chunk_strategy": "chunk_by_canvas_or_frame",
        "large_model_required": False,
        "logs": _append_log(state, f"[graph] stratégie = chunking ({chars} chars)"),
    }


def choose_strategy_router(
    state: PlannerGraphState,
) -> Literal["single_call", "chunk_by_canvas_or_frame"]:
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
            "logs": _append_log(
                state,
                f"[graph] {chunk_count} chunks → modèle large requis"
            ),
        }

    return {
        "planner_chunks": chunks,
        "chunk_count": chunk_count,
        "large_model_required": False,
        "logs": _append_log(state, f"[graph] {chunk_count} chunks -> {PLANNER_CHUNKS_FILE}"),
    }


# ---------------------------------------------------------------------------
# Phase 3 : Génération LLM du Planning
# ---------------------------------------------------------------------------

def llm_generate_planning_node(state: PlannerGraphState) -> dict[str, Any]:
    payload = state["planner_payload"]
    summary = state.get("planner_summary", {})
    chunks = state.get("planner_chunks")             
    use_large = state.get("large_model_required", False)

    chunks_to_send = chunks if state.get("chunk_strategy") != "single_call" else None

    planning = generate_planning(
        payload=payload,
        chunks=chunks_to_send,
        global_summary=summary,
        use_large_model=use_large,
    )

    return {
        "llm_planning": planning,
        "logs": _append_log(
            state,
            f"[graph] Planning LLM généré : "
            f"{len(planning.get('files', []))} fichiers, "
            f"{len(planning.get('folders', []))} dossiers"
        ),
    }


def save_planning_node(state: PlannerGraphState) -> dict[str, Any]:
    planning = state["llm_planning"]
    _save_json(PLANNER_PLANNING_FILE, planning)
    return {
        "logs": _append_log(state, f"[graph] Planning sauvegardé -> {PLANNER_PLANNING_FILE}"),
    }


# ---------------------------------------------------------------------------
# Construction du graph principal
# ---------------------------------------------------------------------------

def build_figma_planner_graph():
    builder = StateGraph(PlannerGraphState)

    # --- Noeuds Phase 1 ---
    builder.add_node("load_or_fetch_raw", load_or_fetch_raw_node)
    builder.add_node("filter_canvases", filter_canvases_node)
    builder.add_node("clean_tree", clean_tree_node)
    builder.add_node("extract_reusable_components", extract_reusable_components_node)

    # --- Noeuds Phase 2 ---
    builder.add_node("build_planner_payload", build_planner_payload_node)
    builder.add_node("estimate_payload_size", estimate_payload_size_node)
    builder.add_node("build_summary", build_summary_node)
    builder.add_node("choose_strategy", choose_strategy_node)
    builder.add_node("build_chunks", build_chunks_node)

    # --- Noeuds Phase 3 ---
    builder.add_node("llm_generate_planning", llm_generate_planning_node)
    builder.add_node("save_planning", save_planning_node)

    # --- Noeuds Phase 4 : Pré-traitement & Scaffolding ---
    builder.add_node("apply_style_system", style_converter_node)
    builder.add_node("map_routes", route_mapper_node)
    builder.add_node("scaffold_project", scaffold_project_node) # Appelle le vrai scaffolder Vite

    # --- Noeuds Phase 5 : Intégration des Vrais Agents (Sous-graphes) ---
    
    
    builder.add_node("codegen", codegen_node)
    #builder.add_node("validation", validation_node)
    
    
    
    
    


    # ====================================================================
    # EDGES (Le flux de données)
    # ====================================================================

    # --- Edges Phase 1 ---
    builder.add_edge(START, "load_or_fetch_raw")
    builder.add_edge("load_or_fetch_raw", "filter_canvases")
    builder.add_edge("filter_canvases", "clean_tree")
    builder.add_edge("clean_tree", "extract_reusable_components")
    builder.add_edge("extract_reusable_components", "build_planner_payload")

    # --- Edges Phase 2 ---
    builder.add_edge("build_planner_payload", "estimate_payload_size")
    builder.add_edge("estimate_payload_size", "build_summary")
    builder.add_edge("build_summary", "choose_strategy")

    builder.add_conditional_edges(
        "choose_strategy",
        choose_strategy_router,
        {
            "single_call": "llm_generate_planning",
            "chunk_by_canvas_or_frame": "build_chunks",
        },
    )

    builder.add_edge("build_chunks", "llm_generate_planning")

    # --- Edges Phase 3, 4 & 5 (La ligne directrice finale) ---
    builder.add_edge("llm_generate_planning", "save_planning")
    #builder.add_edge("save_planning", "apply_style_system")
    builder.add_edge("save_planning", "apply_style_system")
    builder.add_edge("apply_style_system", "map_routes")
    builder.add_edge("map_routes", "scaffold_project")
    builder.add_edge("scaffold_project", "codegen")
    builder.add_edge("codegen", END)
    #builder.add_edge("validation", END)

    #builder.add_edge("apply_style_system", "map_routes")
    #builder.add_edge("map_routes", "scaffold_project")
    
    # Transition vers l'agent Codegen
    #builder.add_edge("scaffold_project", "prep_codegen")
    #builder.add_edge("prep_codegen", "codegen_agent")
    
    # Fin du pipeline (Validateur désactivé temporairement pour voir le code)
    #builder.add_edge("codegen_agent", END)
    
    # Fin du pipeline
    #builder.add_edge("validation_agent", END)

    return builder.compile()


# Point d'entrée pour ton main.py
graph = build_figma_planner_graph()