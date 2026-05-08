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
    PLANNER_INPUT_FILE,
    
    
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
from services.planner.planner_input_builder import build_planner_input

from llm.planner import generate_planning


# Imports des nouvelles étapes
#from services.figma.style_converter import style_converter_node
#from services.figma.route_mapper import route_mapper_node 






#from agents.codegen_agent import scaffold_project_node, codegen_runner_node
#from agents.validation_agent import validation_agent_node
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
 
 
def _append_log(state, message: str) -> list[str]:
    logs = list(state.get("logs", []))
    logs.append(message)
    return logs
 
 
# ---------------------------------------------------------------------------
# Nœud 1 : Construire l'input du LLM de planning
# ---------------------------------------------------------------------------
 
def build_planner_input_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Lit le JSON nettoyé + les composants réutilisables,
    construit le payload pour le LLM de planning,
    découpe en chunks si nécessaire.
    """
    # Lire le JSON nettoyé depuis le fichier
    with open(CLEANED_OUTPUT_FILE, "r", encoding="utf-8") as f:
        cleaned_json = json.load(f)
 
    # Les composants réutilisables sont déjà dans le state
    reusable_data = state["reusable_components"]
 
    # Construire l'input (chunking inclus)
    planner_input = build_planner_input(
        cleaned_json=cleaned_json,
        reusable_data=reusable_data,
        max_depth=PLANNER_MAX_DEPTH,
        max_chars_per_chunk=PLANNER_MAX_CHARS_PER_CHUNK,
    )
 
    # Sauvegarder
    _save_json(PLANNER_INPUT_FILE, planner_input)
 
    # Stats pour le log
    stats = planner_input["stats"]
    chunk_count = planner_input["total_chunks"]
 
    return {
        "planner_input": planner_input,
        "logs": _append_log(
            state,
            f"[graph] planner input construit : "
            f"{stats['total_pages']} pages, "
            f"{chunk_count} chunk(s), "
            f"sauvegardé -> {PLANNER_INPUT_FILE}",
        ),
    }
 
 
# ---------------------------------------------------------------------------
# Nœud 2 : Vérifier la faisabilité (trop de chunks ?)
# ---------------------------------------------------------------------------
 
def check_planner_feasibility_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Vérifie si le nombre de chunks est raisonnable pour le LLM.
    Si trop de chunks → on flag pour utiliser un modèle à plus grand context.
    """
    planner_input = state["planner_input"]
    chunk_count = planner_input["total_chunks"]
 
    if chunk_count > PLANNER_MAX_CHUNKS:
        return {
            "planner_feasibility": "large_model_required",
            "logs": _append_log(
                state,
                f"[graph] {chunk_count} chunks dépasse le max ({PLANNER_MAX_CHUNKS}) "
                f"→ modèle large requis",
            ),
        }
 
    return {
        "planner_feasibility": "ready",
        "logs": _append_log(
            state,
            f"[graph] {chunk_count} chunk(s) → prêt pour le LLM de planning",
        ),
    }
 
 
def planner_feasibility_router(
    state: dict[str, Any],
) -> Literal["ready", "large_model_required"]:
    """Router conditionnel après check_planner_feasibility_node."""
    return state["planner_feasibility"]

# ---------------------------------------------------------------------------
# Phase 3 : Génération LLM du Planning
# ---------------------------------------------------------------------------

def llm_generate_planning_node(state: PlannerGraphState) -> dict[str, Any]:
    planner_input = state["planner_input"]

    planning = generate_planning(planner_input=planner_input)

    return {
        "llm_planning": planning,
        "logs": _append_log(
            state,
            f"[graph] Planning généré : "
            f"{len(planning.get('pages', []))} pages, "
            f"{len(planning.get('generation_order', []))} étapes",
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
    builder.add_node("build_planner_input", build_planner_input_node)
    builder.add_node("check_planner_feasibility", check_planner_feasibility_node)

    # --- Noeuds Phase 3 ---
    builder.add_node("llm_generate_planning", llm_generate_planning_node)
    builder.add_node("save_planning", save_planning_node)

    # --- Noeuds Phase 4 : Pré-traitement & Scaffolding ---
    #builder.add_node("apply_style_system", style_converter_node)
    #builder.add_node("map_routes", route_mapper_node)
    
    #builder.add_node("scaffold_project", scaffold_project_node)
    #builder.add_node("codegen", codegen_runner_node)
    #builder.add_node("validation", validation_agent_node)

    
    
    
    


    # ====================================================================
    # EDGES (Le flux de données)
    # ====================================================================

    # --- Edges Phase 1 ---
    builder.add_edge(START, "load_or_fetch_raw")
    builder.add_edge("load_or_fetch_raw", "filter_canvases")
    builder.add_edge("filter_canvases", "clean_tree")
    builder.add_edge("clean_tree", "extract_reusable_components")
    builder.add_edge("extract_reusable_components", "build_planner_input")
    builder.add_edge("build_planner_input", "check_planner_feasibility")
    builder.add_conditional_edges(
      "check_planner_feasibility",
       planner_feasibility_router,
       {
           "ready": "llm_generate_planning",
           "large_model_required": "llm_generate_planning", 
        },
    )  
    #builder.add_edge("llm_generate_planning", "scaffold_project")
    #builder.add_edge("scaffold_project", "codegen")
    #builder.add_edge("codegen", "validation")
    #builder.add_edge("validation", END)
    #builder.add_edge("extract_reusable_components", "build_planner_payload")
    """
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
    #builder.add_edge("save_planning", "apply_style_system")
    #builder.add_edge("apply_style_system", "map_routes")

    builder.add_edge("save_planning","map_routes" )
    builder.add_edge("map_routes", "scaffold_project")
    
    builder.add_edge("scaffold_project", "analyste")
    builder.add_edge("analyste", "architecte")
# builder.add_edge("architecte", "extract_sections")
# builder.add_edge("extract_sections", "generateur")
    builder.add_edge("architecte", "generateur") # Si tu ne l'automatises pas, lance le script à la main avant
    builder.add_edge("generateur", END)

    #builder.add_edge("apply_style_system", "map_routes")
    #builder.add_edge("map_routes", "scaffold_project")
    
    # Transition vers l'agent Codegen
    #builder.add_edge("scaffold_project", "prep_codegen")
    #builder.add_edge("prep_codegen", "codegen_agent")
    
    # Fin du pipeline (Validateur désactivé temporairement pour voir le code)
    #builder.add_edge("codegen_agent", END)
    
    # Fin du pipeline
    #builder.add_edge("validation_agent", END)
"""
    return builder.compile()


# Point d'entrée pour ton main.py
graph = build_figma_planner_graph()