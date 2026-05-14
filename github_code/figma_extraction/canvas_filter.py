import copy
from .canvas_blacklist import CANVAS_BLACKLIST


def _is_blacklisted(name: str) -> bool:
    """
    Retourne True si le nom du canvas correspond à un mot de la blacklist.
    Matching insensible à la casse et partiel (substring).
    """
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in CANVAS_BLACKLIST)


def filter_canvases(raw_data: dict) -> dict:
    """
    Filtre les canvases (pages Figma) inutiles depuis le JSON brut.
    Opère sur une copie — ne modifie jamais raw_data.
    """
    data = copy.deepcopy(raw_data)

    document = data.get("document", {})
    canvases = document.get("children", [])

    before = len(canvases)
    kept = [c for c in canvases if not _is_blacklisted(c.get("name", ""))]
    after = len(kept)

    removed = [c.get("name", "?") for c in canvases if _is_blacklisted(c.get("name", ""))]

    if removed:
        print(f"[canvas_filter] Canvases supprimés ({before - after}) : {removed}")
    print(f"[canvas_filter] Canvases conservés ({after}) : {[c.get('name') for c in kept]}")

    data["document"]["children"] = kept
    return data