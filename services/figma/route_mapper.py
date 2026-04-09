"""
services/figma/route_mapper.py
----------------------------------
Noeud de conversion des interactions Figma (ON_CLICK -> NAVIGATE) 
en instructions de routage React (react-router-dom).
Lit : data/planner/planning.json & data/code_style/processed.json
Écrit : data/code_style/processed.json (écrasé et enrichi)
"""

import json
from pathlib import Path

# --- Chemins ---
PLANNING_FILE = Path("data/planner/planning.json")
PROCESSED_FILE = Path("data/code_style/processed.json")


def _build_route_mapping(planning: dict) -> dict[str, str]:
    """
    Crée un dictionnaire de correspondance : { "figma_node_id": "/url_react" }
    Ex: { "636:315": "/features", "601:615": "/" }
    """
    mapping = {}
    
    # On boucle sur les fichiers définis dans le planning
    for file_info in planning.get("files", []):
        # On ne s'intéresse qu'aux pages (qui ont une route)
        if file_info.get("type") == "page" and file_info.get("figma_node_id"):
            node_id = file_info["figma_node_id"]
            component_name = file_info.get("component_name")
            
            # On cherche le path correspondant dans la liste des routes
            for route in planning.get("routes", []):
                if route.get("page_component") == component_name:
                    mapping[node_id] = route.get("path")
                    break
                    
    return mapping


def _process_node(node: dict, route_map: dict[str, str]) -> dict:
    """
    Parcourt chaque noeud. S'il a une interaction de navigation,
    il ajoute "react_routing" et supprime "interactions".
    """
    if not isinstance(node, dict):
        return node

    interactions = node.get("interactions")
    
    # Vérifie si le noeud a des interactions et que c'est une liste
    if interactions and isinstance(interactions, list):
        for interaction in interactions:
            trigger = interaction.get("trigger", {})
            actions = interaction.get("actions", [])
            
            # C'est un clic ?
            if trigger.get("type") == "ON_CLICK":
                for action in actions:
                    # C'est une navigation ?
                    if action.get("navigation") == "NAVIGATE":
                        dest_id = action.get("destinationId")
                        
                        # L'ID de destination correspond-il à une de nos pages React ?
                        if dest_id in route_map:
                            url_path = route_map[dest_id]
                            # ON INJECTE L'INSTRUCTION POUR L'AGENT CODER
                            node["react_routing"] = {
                                "type": "Link", # L'agent saura qu'il faut utiliser <Link to="...">
                                "to": url_path
                            }
        
        # NETTOYAGE : On supprime la vieille interaction Figma devenue inutile
        del node["interactions"]

    # Récursion sur les enfants
    if "children" in node:
        node["children"] = [_process_node(child, route_map) for child in node["children"]]

    return node


# ======================================================================
# FONCTION NOEUD LANGGRAPH
# ======================================================================
def route_mapper_node(state: dict) -> dict:
    print("\n[Route Mapper] Extraction des interactions Figma et conversion en routes React...")
    
    if not PLANNING_FILE.exists() or not PROCESSED_FILE.exists():
        print("[Route Mapper] ❌ Fichiers manquants, étape ignorée.")
        return {"logs": list(state.get("logs", []))}

    # 1. Créer le dictionnaire ID -> URL
    with open(PLANNING_FILE, "r", encoding="utf-8") as f:
        planning = json.load(f)
    route_map = _build_route_mapping(planning)
    print(f"[Route Mapper] {len(route_map)} route(s) React trouvée(s) dans le planning.")

    # 2. Parcourir et transformer le JSON
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        processed_data = json.load(f)

    # On cible le bon endroit (comme pour le style converter)
    if "document" in processed_data:
        processed_data["document"] = _process_node(processed_data["document"], route_map)
    else:
        processed_data = _process_node(processed_data, route_map)

    # 3. Sauvegarder
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)

    print("[Route Mapper] ✅ JSON enrichi avec 'react_routing' et sauvegardé !\n")
    
    logs = list(state.get("logs", []))
    logs.append("[Route Mapper] Interactions Figma converties en routes React.")
    return {"logs": logs}