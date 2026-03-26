from typing import Any


def build_global_summary(planner_payload: dict[str, Any]) -> dict[str, Any]:
    figma_tree = planner_payload.get("figma_tree", {})
    canvases = figma_tree.get("document", {}).get("children", [])
    reusable_components = planner_payload.get("reusable_components", [])

    canvas_summaries = []
    for canvas in canvases:
        children = canvas.get("children", [])
        canvas_summaries.append({
            "id": canvas.get("id"),
            "name": canvas.get("name"),
            "type": canvas.get("type"),
            "top_level_blocks_count": len(children),
            "top_level_block_names": [child.get("name") for child in children[:10]],
        })

    reusable_summary = [
        {
            "component_id": comp.get("component_id"),
            "name": comp.get("name"),
            "total_instances": comp.get("total_instances"),
        }
        for comp in reusable_components[:20]
    ]

    return {
        "total_canvases": figma_tree.get("total_canvases", 0),
        "canvas_summaries": canvas_summaries,
        "reusable_components_count": len(reusable_components),
        "top_reusable_components": reusable_summary,
    }