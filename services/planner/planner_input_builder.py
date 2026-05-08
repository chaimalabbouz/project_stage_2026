"""
planner_input_builder.py
========================
Construit l'input pour le LLM de planning.

Le LLM de planning reçoit :
  - L'arbre Figma limité en profondeur (structure globale, pas les détails)
  - La liste légère des composants réutilisables (juste noms et kinds)

Et il produit le plan de génération : quelles pages, quelles sections,
dans quel ordre générer.

Si le payload est trop gros pour un seul appel LLM, on le découpe
en chunks (un par page/frame de premier niveau).

Les routes et la navigation ne sont PAS gérées ici — elles seront
détectées plus tard via l'analyse des interactions Figma.
"""

import json
from typing import Any

from services.planner.size_estimator import estimate_json_size


# ---------------------------------------------------------------------------
# Arbre limité en profondeur
# ---------------------------------------------------------------------------

_TREE_FIELDS = {"id", "name", "type", "layoutMode", "componentId"}


def _build_limited_node(
    node: dict[str, Any],
    current_depth: int,
    max_depth: int,
) -> dict[str, Any]:
    """
    Copie un nœud Figma en ne gardant que les champs structurels,
    et en coupant la récursion à max_depth.

    Au-delà de max_depth, on indique juste qu'il y a des enfants
    (has_children + children_count) sans les détailler.
    """
    limited = {key: node[key] for key in _TREE_FIELDS if key in node}

    children = node.get("children", [])
    has_children = isinstance(children, list) and len(children) > 0

    if current_depth < max_depth:
        if has_children:
            limited["children"] = [
                _build_limited_node(child, current_depth + 1, max_depth)
                for child in children
            ]
    else:
        if has_children:
            limited["has_children"] = True
            limited["children_count"] = len(children)

    return limited


# ---------------------------------------------------------------------------
# Résumé léger des composants réutilisables
# ---------------------------------------------------------------------------

def _lighten_reusable_components(
    reusable_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Produit un résumé minimal des composants pour le planning.
    Le LLM de planning a juste besoin de savoir quels composants existent.
    """
    result = []

    for comp in reusable_data.get("standalone", []):
        result.append({
            "kind": "standalone",
            "component_id": comp.get("component_id"),
            "name": comp.get("name"),
        })

    for vset in reusable_data.get("variant_sets", []):
        result.append({
            "kind": "variant_set",
            "component_set_id": vset.get("component_set_id"),
            "name": vset.get("name"),
        })

    return result


# ---------------------------------------------------------------------------
# Chunking : découpe si le payload est trop gros
# ---------------------------------------------------------------------------

def _split_into_chunks(
    limited_canvases: list[dict[str, Any]],
    reusable_summary: list[dict[str, Any]],
    max_chars: int,
) -> list[dict[str, Any]]:
    """
    Si le payload total dépasse max_chars, on produit un chunk par
    frame de premier niveau (= par page).

    Chaque chunk contient :
      - La frame/page concernée
      - Les composants réutilisables (légers, partagés dans tous les chunks)

    Si tout tient dans max_chars, on retourne un seul chunk avec tout.
    """

    # Tester d'abord si tout tient en un seul morceau
    full_payload = {
        "canvases": limited_canvases,
        "reusable_components": reusable_summary,
    }

    size = estimate_json_size(full_payload)
    if size["chars"] <= max_chars:
        return [full_payload]

    # Sinon, découper par frame de premier niveau
    chunks = []

    for canvas in limited_canvases:
        top_frames = canvas.get("children", [])

        if not top_frames:
            chunks.append({
                "canvas_name": canvas.get("name"),
                "frame": canvas,
                "reusable_components": reusable_summary,
            })
            continue

        for frame in top_frames:
            chunk = {
                "canvas_name": canvas.get("name"),
                "frame": frame,
                "reusable_components": reusable_summary,
            }

            # Si un chunk est encore trop gros, réduire la profondeur
            chunk_size = estimate_json_size(chunk)
            if chunk_size["chars"] > max_chars:
                reduced = _build_limited_node(frame, current_depth=1, max_depth=2)
                chunk["frame"] = reduced
                chunk["_warning"] = "frame reduced to depth 2 (too large)"

            chunks.append(chunk)

    return chunks


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def build_planner_input(
    cleaned_json: dict[str, Any],
    reusable_data: dict[str, Any],
    max_depth: int = 4,
    max_chars_per_chunk: int = 80_000,
) -> dict[str, Any]:
    """
    Construit l'input complet pour le LLM de planning.

    Params:
        cleaned_json: le JSON Figma nettoyé (figma_cleaned.json)
        reusable_data: la sortie de extract_reusable_components()
        max_depth: profondeur max de l'arbre pour le planning
        max_chars_per_chunk: taille max d'un chunk en caractères

    Returns:
        {
            "chunks": [...],
            "total_chunks": int,
            "stats": {
                "total_pages": int,
                "total_standalone_components": int,
                "total_variant_sets": int,
            }
        }
    """
    canvases = cleaned_json.get("document", {}).get("children", [])

    # 1. Arbre limité en profondeur
    limited_canvases = [
        _build_limited_node(canvas, current_depth=1, max_depth=max_depth)
        for canvas in canvases
    ]

    # 2. Résumé léger des composants
    reusable_summary = _lighten_reusable_components(reusable_data)

    # 3. Chunking si nécessaire
    chunks = _split_into_chunks(
        limited_canvases=limited_canvases,
        reusable_summary=reusable_summary,
        max_chars=max_chars_per_chunk,
    )

    # 4. Stats pour le logging
    total_pages = sum(
        len(canvas.get("children", []))
        for canvas in canvases
    )

    return {
        "chunks": chunks,
        "total_chunks": len(chunks),
        "stats": {
            "total_pages": total_pages,
            "total_standalone_components": len(reusable_data.get("standalone", [])),
            "total_variant_sets": len(reusable_data.get("variant_sets", [])),
        },
    }