import json
from typing import Any


def estimate_json_size(data: dict[str, Any]) -> dict[str, int]:
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    chars = len(compact)
    estimated_tokens = max(1, chars // 4)

    return {
        "chars": chars,
        "estimated_tokens": estimated_tokens,
    }
    """
    ce ficheir essaye d estimer le nbre de token de fichie  planner_playload
    """