import copy
from typing import Any, Dict, List


FIELDS_LAYOUT = {
    "layoutMode",
    "primaryAxisAlignItems",
    "counterAxisAlignItems",
    "primaryAxisSizingMode",
    "counterAxisSizingMode",
    "paddingLeft",
    "paddingRight",
    "paddingTop",
    "paddingBottom",
    "itemSpacing",
    "layoutWrap",
    "layoutAlign",
    "layoutGrow",
    "layoutSizingHorizontal",
    "layoutSizingVertical",
    "constraints",
    "clipsContent",
}

LAYOUT_TYPES = {
    "FRAME",
    "GROUP",
    "COMPONENT",
    "COMPONENT_SET",
    "INSTANCE",
    "SECTION",
}

IMAGE_FIELDS = {
    "imageRef",
    "gifRef",
    "scaleMode",
}

BOUNDS_FIELDS = {
    "absoluteBoundingBox",
    "size",
    "relativeTransform",
}

USEFUL_GENERIC_FIELDS = {
    "id",
    "name",
    "type",
    "visible",
    "componentId",
    "componentSetId",
    "description",
    "interactions",
}

ROOT_KEYS_TO_REMOVE = {
    "schemaVersion",
    "styles",
    "componentSets",
    "components",
    "mainFileKey",
    "branches",
}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def _prune_empty(data: Any) -> Any:
    """
    Supprime récursivement:
    - None
    - ""
    - []
    - {}
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            pruned = _prune_empty(value)
            if not _is_empty(pruned):
                cleaned[key] = pruned
        return cleaned

    if isinstance(data, list):
        cleaned_list = []
        for item in data:
            pruned = _prune_empty(item)
            if not _is_empty(pruned):
                cleaned_list.append(pruned)
        return cleaned_list

    return data


def _clean_paint_list(paints: Any) -> List[Dict[str, Any]]:
    """
    Garde seulement les infos utiles des fills/strokes.
    """
    if not isinstance(paints, list):
        return []

    cleaned_paints = []

    for paint in paints:
        if not isinstance(paint, dict):
            continue

        item = {}

        for key in [
            "type",
            "visible",
            "opacity",
            "blendMode",
            "scaleMode",
            "imageRef",
            "gifRef",
            "color",
            "gradientStops",
            "gradientHandlePositions",
        ]:
            if key in paint:
                item[key] = paint[key]

        item = _prune_empty(item)
        if item:
            cleaned_paints.append(item)

    return cleaned_paints


def _clean_effects(effects: Any) -> List[Dict[str, Any]]:
    """
    Garde seulement les infos utiles des effets.
    """
    if not isinstance(effects, list):
        return []

    cleaned_effects = []

    for effect in effects:
        if not isinstance(effect, dict):
            continue

        item = {}
        for key in [
            "type",
            "visible",
            "radius",
            "spread",
            "color",
            "offset",
            "blendMode",
        ]:
            if key in effect:
                item[key] = effect[key]

        item = _prune_empty(item)
        if item:
            cleaned_effects.append(item)

    return cleaned_effects


def _clean_interactions(interactions: Any) -> List[Dict[str, Any]]:
    """
    Garde les interactions non vides pour un futur routing/navigation.
    """
    if not isinstance(interactions, list):
        return []

    cleaned = []
    for interaction in interactions:
        if not isinstance(interaction, dict):
            continue

        simplified = _prune_empty(interaction)
        if simplified:
            cleaned.append(simplified)

    return cleaned


def _clean_text_style(style: Any) -> Dict[str, Any]:
    """
    Garde les infos de police utiles pour générer du code fidèle.
    """
    if not isinstance(style, dict):
        return {}

    useful_keys = [
        "fontFamily",
        "fontPostScriptName",
        "fontWeight",
        "fontSize",
        "textAlignHorizontal",
        "textAlignVertical",
        "letterSpacing",
        "lineHeightPx",
        "lineHeightPercent",
        "lineHeightPercentFontSize",
        "lineHeightUnit",
        "textCase",
        "textDecoration",
        "paragraphSpacing",
        "paragraphIndent",
    ]

    result = {k: style[k] for k in useful_keys if k in style}
    return _prune_empty(result)


def _clean_style_override_table(table: Any) -> Dict[str, Any]:
    """
    Garde les styles de texte enrichi seulement s'ils sont utiles.
    """
    if not isinstance(table, dict):
        return {}

    cleaned = {}
    for key, value in table.items():
        if isinstance(value, dict):
            cleaned_value = _clean_text_style(value)
            if cleaned_value:
                cleaned[key] = cleaned_value

    return cleaned


def _clean_node(node: Dict[str, Any]) -> Dict[str, Any]:
    node_type = node.get("type", "")

    cleaned: Dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
    }

    # Visible
    if "visible" in node and node.get("visible") is False:
        cleaned["visible"] = False

    # Champs génériques utiles
    for key in USEFUL_GENERIC_FIELDS:
        if key in node and key not in {"id", "name", "type", "visible", "interactions"}:
            cleaned[key] = node[key]

    # Layout
    if node_type in LAYOUT_TYPES:
        for key in FIELDS_LAYOUT:
            if key in node:
                cleaned[key] = node[key]

    # Bounds / position / taille
    for key in BOUNDS_FIELDS:
        if key in node:
            cleaned[key] = node[key]

    # Texte
    if node_type == "TEXT":
        if "characters" in node:
            cleaned["characters"] = node["characters"]

        if "style" in node:
            style = _clean_text_style(node["style"])
            if style:
                cleaned["style"] = style

        overridden_fields = node.get("overriddenFields", [])

        has_style_overrides = (
            "characterStyleOverrides" in node
            and isinstance(node["characterStyleOverrides"], list)
            and len(node["characterStyleOverrides"]) > 0
            and "characterStyleOverrides" in overridden_fields
        )

        has_override_table = (
            "styleOverrideTable" in node
            and isinstance(node["styleOverrideTable"], dict)
            and len(node["styleOverrideTable"]) > 0
            and "styleOverrideTable" in overridden_fields
        )

        if has_style_overrides:
            cleaned["characterStyleOverrides"] = node["characterStyleOverrides"]

        if has_override_table:
            table = _clean_style_override_table(node["styleOverrideTable"])
            if table:
                cleaned["styleOverrideTable"] = table

        if overridden_fields:
            relevant_overrides = [
                field
                for field in overridden_fields
                if field in {"characterStyleOverrides", "styleOverrideTable", "characters"}
            ]
            if relevant_overrides:
                cleaned["overriddenFields"] = relevant_overrides

    # Styles visuels
    if "fills" in node:
        fills = _clean_paint_list(node["fills"])
        if fills:
            cleaned["fills"] = fills

    if "strokes" in node:
        strokes = _clean_paint_list(node["strokes"])
        if strokes:
            cleaned["strokes"] = strokes

    if "effects" in node:
        effects = _clean_effects(node["effects"])
        if effects:
            cleaned["effects"] = effects

    for key in [
        "strokeWeight",
        "individualStrokeWeights",
        "strokeAlign",
        "strokeDashes",
        "cornerRadius",
        "rectangleCornerRadii",
        "cornerSmoothing",
        "opacity",
        "blendMode",
        "backgroundColor",
        "background",
        "backgrounds",
    ]:
        if key in node:
            cleaned[key] = node[key]

    # Images
    for key in IMAGE_FIELDS:
        if key in node:
            cleaned[key] = node[key]

    # Interactions utiles seulement si non vides
    if "interactions" in node:
        interactions = _clean_interactions(node["interactions"])
        if interactions:
            cleaned["interactions"] = interactions

    # Enfants
    if "children" in node and isinstance(node["children"], list):
        cleaned_children = [_clean_node(child) for child in node["children"] if isinstance(child, dict)]
        if cleaned_children:
            cleaned["children"] = cleaned_children

    return _prune_empty(cleaned)


def clean_tree(filtered_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nettoie le JSON Figma filtré en gardant:
    - structure
    - layout
    - texte
    - styles utiles
    - images
    - interactions utiles

    Supprime:
    - champs vides
    - blocs racine inutiles
    - beaucoup de bruit non exploitable
    """
    data = copy.deepcopy(filtered_data)

    canvases = data.get("document", {}).get("children", [])
    cleaned_canvases = []

    for canvas in canvases:
        cleaned_canvas = {
            "id": canvas.get("id"),
            "name": canvas.get("name"),
            "type": canvas.get("type"),
        }

        if "children" in canvas and isinstance(canvas["children"], list):
            cleaned_children = [_clean_node(child) for child in canvas["children"] if isinstance(child, dict)]
            if cleaned_children:
                cleaned_canvas["children"] = cleaned_children

        cleaned_canvas = _prune_empty(cleaned_canvas)
        cleaned_canvases.append(cleaned_canvas)

    # Nettoyage racine
    for key in ROOT_KEYS_TO_REMOVE:
        data.pop(key, None)

    data["document"] = {"children": cleaned_canvases}
    data = _prune_empty(data)

    print(f"[cleaner] {len(cleaned_canvases)} canvas(es) nettoyé(s).")
    return data