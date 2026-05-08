import json
from pathlib import Path
from config.settings import MINIMAL_OUTPUT_FILE, TREE_OUTPUT_FILE


def _limit_depth(node: dict, current_level: int, max_level: int) -> dict:
    cleaned = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
    }

    if node.get("type") == "TEXT" and "characters" in node:
        cleaned["characters"] = node["characters"]

    if "layoutMode" in node:
        cleaned["layoutMode"] = node["layoutMode"]

    if "componentId" in node:
        cleaned["componentId"] = node["componentId"]

    if current_level < max_level and "children" in node:
        cleaned["children"] = [
            _limit_depth(child, current_level + 1, max_level)
            for child in node["children"]
        ]
    elif "children" in node:
        cleaned["has_children"] = True
        cleaned["children_count"] = len(node["children"])

    return cleaned


def extract_tree_3levels(minimal_path: Path = MINIMAL_OUTPUT_FILE, max_level: int = 3) -> dict:
    print("\n[tree_extractor] Chargement du JSON minimal...")
    with open(minimal_path, "r", encoding="utf-8") as f:
        tree = json.load(f)

    canvases = tree.get("document", {}).get("children", [])
    limited_canvases = []

    for canvas in canvases:
        limited_canvas = {
            "id": canvas.get("id"),
            "name": canvas.get("name"),
            "type": canvas.get("type"),
            "children": [
                _limit_depth(child, current_level=1, max_level=max_level)
                for child in canvas.get("children", [])
            ]
        }
        limited_canvases.append(limited_canvas)

    result = {
        "max_depth": max_level,
        "total_canvases": len(limited_canvases),
        "document": {
            "children": limited_canvases
        }
    }

    TREE_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TREE_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = TREE_OUTPUT_FILE.stat().st_size / 1024
    print(f"[tree_extractor] Arbre {max_level} niveaux extrait — {len(limited_canvases)} canvas(es).")
    print(f"[tree_extractor] Sauvegardé -> {TREE_OUTPUT_FILE}  ({size_kb:.1f} KB)")

    return result