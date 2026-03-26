import copy

FIELDS_LAYOUT = {
    "layoutMode",
    "primaryAxisAlignItems",
    "counterAxisAlignItems",
    "paddingLeft",
    "paddingRight",
    "paddingTop",
    "paddingBottom",
    "itemSpacing",
    "layoutWrap",
    "componentId",
    "componentSetId",
}

LAYOUT_TYPES = {
    "FRAME",
    "GROUP",
    "COMPONENT",
    "COMPONENT_SET",
    "INSTANCE",
    "SECTION",
}


def _clean_node(node: dict) -> dict:
    node_type = node.get("type", "")

    # Base minimale commune
    cleaned = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
    }

    # Si le node est invisible, on le garde en version minimale
    if not node.get("visible", True):
        cleaned["hidden"] = True
        return cleaned

    # Si c'est un node de layout, on garde quelques champs utiles
    if node_type in LAYOUT_TYPES:
        for key in FIELDS_LAYOUT:
            if key in node:
                cleaned[key] = node[key]

    # Si c'est un TEXT, on garde seulement le contenu
    if node_type == "TEXT":
        if "characters" in node:
            cleaned["characters"] = node["characters"]

    # Récursion sur les enfants
    if "children" in node and isinstance(node["children"], list):
        cleaned["children"] = [_clean_node(child) for child in node["children"]]

    return cleaned


def clean_tree(filtered_data: dict) -> dict:
    """
    Nettoie le JSON Figma filtré pour ne garder que les informations utiles au LLM.
    Ne supprime aucun node, mais réduit fortement les champs.
    """
    data = copy.deepcopy(filtered_data)
    canvases = data.get("document", {}).get("children", [])

    cleaned_canvases = []
    for canvas in canvases:
        cleaned_canvas = {
            "id": canvas.get("id"),
            "name": canvas.get("name"),
            "type": canvas.get("type"),
            "children": [_clean_node(child) for child in canvas.get("children", [])],
        }
        cleaned_canvases.append(cleaned_canvas)

    # Nettoyage racine : on enlève les gros blocs inutiles
    for key in [
        "schemaVersion",
        "styles",
        "componentSets",
        "components",
        "mainFileKey",
        "branches",
    ]:
        data.pop(key, None)

    data["document"] = {"children": cleaned_canvases}
    print(f"[cleaner] {len(cleaned_canvases)} canvas(es) nettoyé(s) — aucun node supprimé.")
    return data