import json
from pathlib import Path
from config.settings import RAW_OUTPUT_FILE


def find_node_by_id(node: dict, target_id: str) -> dict | None:
    if node.get("id") == target_id:
        return node
    for child in node.get("children", []):
        result = find_node_by_id(child, target_id)
        if result is not None:
            return result
    return None


def find_node_in_raw(target_id: str, raw_path: Path = RAW_OUTPUT_FILE) -> dict | None:
    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    for canvas in raw.get("document", {}).get("children", []):
        result = find_node_by_id(canvas, target_id)
        if result is not None:
            return result
    return None