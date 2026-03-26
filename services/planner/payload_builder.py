from typing import Any

DEFAULT_NODE_FIELDS = {
    "id",
    "name",
    "type",
    "layoutMode",
    "componentId",
}


def _build_limited_node(
    node: dict[str, Any],
    current_depth: int,
    max_depth: int,
) -> dict[str, Any]:
    limited = {
        key: node[key]
        for key in DEFAULT_NODE_FIELDS
        if key in node
    }

    children = node.get("children", [])
    has_children = isinstance(children, list) and len(children) > 0

    if current_depth >= max_depth:
        if has_children:
            limited["has_children"] = True
            limited["children_count"] = len(children)
        return limited

    if has_children:
        limited["children"] = [
            _build_limited_node(child, current_depth + 1, max_depth)
            for child in children
        ]

    return limited


def _lighten_reusable_components(reusable_components_data: dict[str, Any]) -> list[dict[str, Any]]:
    result = []

    for comp in reusable_components_data.get("components", []):
        result.append({
            "component_id": comp.get("component_id"),
            "name": comp.get("name"),
            "total_instances": comp.get("total_instances", 0),
            "used_in_frames": comp.get("used_in_frames", []),
        })

    result.sort(key=lambda x: x.get("total_instances", 0), reverse=True)
    return result


def build_planner_payload(
    cleaned_json: dict[str, Any],
    reusable_components_data: dict[str, Any],
    max_depth: int = 3,
) -> dict[str, Any]:
    canvases = cleaned_json.get("document", {}).get("children", [])

    limited_canvases = [
        _build_limited_node(canvas, current_depth=1, max_depth=max_depth)
        for canvas in canvases
    ]

    payload = {
        "figma_tree": {
            "max_depth": max_depth,
            "total_canvases": len(limited_canvases),
            "document": {
                "children": limited_canvases
            },
        },
        "reusable_components": _lighten_reusable_components(reusable_components_data),
    }

    return payload

 """
 ce fichier est fait pour construire le input de llm qui va nous donner l architecture
 il rend le json nettpyé en 3 level et aussi ajoute les composants reutilisable 
 """
 