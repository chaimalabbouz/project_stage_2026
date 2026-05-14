"""
component_reu.py
================
Extrait les composants réutilisables depuis le canvas "Components" du JSON Figma.

Responsabilité UNIQUE : produire un catalogue propre de composants
(standalone + variant sets) avec leurs définitions visuelles et props.

Ne s'occupe PAS du canvas design ni des instances — c'est le rôle
du parser de pages.
"""

import json
from pathlib import Path
from typing import Any

from config.settings import RAW_OUTPUT_FILE, COMPONENT_REU_OUTPUT_FILE


# ---------------------------------------------------------------------------
# Mots-clés pour identifier le canvas des composants réutilisables
# ---------------------------------------------------------------------------

COMPONENTS_CANVAS_KEYWORDS = [
    "component",
    "style guide",
    "styleguide",
    "design system",
    "library",
]


# ---------------------------------------------------------------------------
# Champs à extraire selon le contexte
# ---------------------------------------------------------------------------

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

BOUNDS_FIELDS = {
    "absoluteBoundingBox",
    "size",
    "relativeTransform",
}

IMAGE_FIELDS = {
    "imageRef",
    "gifRef",
    "scaleMode",
}

STYLE_FIELDS = {
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
}

USEFUL_GENERIC_FIELDS = {
    "id",
    "name",
    "type",
    "visible",
    "componentId",
    "componentSetId",
    "description",
}


# ---------------------------------------------------------------------------
# Helpers de nettoyage
# ---------------------------------------------------------------------------

def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def _prune_empty(data: Any) -> Any:
    """Supprime récursivement les clés/valeurs vides (None, [], {}, '')."""
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


def _clean_paint_list(paints: Any) -> list[dict]:
    """Nettoie une liste de fills ou strokes Figma."""
    if not isinstance(paints, list):
        return []

    cleaned = []
    for paint in paints:
        if not isinstance(paint, dict):
            continue

        item = {}
        for key in (
            "type", "visible", "opacity", "blendMode", "scaleMode",
            "imageRef", "gifRef", "color",
            "gradientStops", "gradientHandlePositions",
        ):
            if key in paint:
                item[key] = paint[key]

        item = _prune_empty(item)
        if item:
            cleaned.append(item)

    return cleaned


def _clean_effects(effects: Any) -> list[dict]:
    """Nettoie une liste d'effets (ombres, blur, etc.)."""
    if not isinstance(effects, list):
        return []

    cleaned = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue

        item = {}
        for key in ("type", "visible", "radius", "spread", "color", "offset", "blendMode"):
            if key in effect:
                item[key] = effect[key]

        item = _prune_empty(item)
        if item:
            cleaned.append(item)

    return cleaned


def _clean_text_style(style: Any) -> dict:
    """Extrait les propriétés typographiques utiles."""
    if not isinstance(style, dict):
        return {}

    useful_keys = (
        "fontFamily", "fontPostScriptName", "fontWeight", "fontSize",
        "textAlignHorizontal", "textAlignVertical",
        "letterSpacing", "lineHeightPx", "lineHeightPercent",
        "lineHeightPercentFontSize", "lineHeightUnit",
        "textCase", "textDecoration",
        "paragraphSpacing", "paragraphIndent",
    )

    result = {k: style[k] for k in useful_keys if k in style}
    return _prune_empty(result)


def _clean_style_override_table(table: Any) -> dict:
    """Nettoie la table de style overrides pour les nœuds TEXT."""
    if not isinstance(table, dict):
        return {}

    cleaned = {}
    for key, value in table.items():
        if isinstance(value, dict):
            cleaned_value = _clean_text_style(value)
            if cleaned_value:
                cleaned[key] = cleaned_value

    return cleaned


# ---------------------------------------------------------------------------
# Nettoyage d'un nœud Figma
# ---------------------------------------------------------------------------

def _clean_node(node: dict) -> dict:
    """
    Nettoie un nœud Figma en gardant uniquement les informations
    nécessaires pour générer du code React + Tailwind.
    """
    node_type = node.get("type", "")

    cleaned = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
    }

    # Champs génériques
    for key in USEFUL_GENERIC_FIELDS:
        if key in node and key not in ("id", "name", "type"):
            cleaned[key] = node[key]

    # Layout (flex, padding, gap, etc.)
    if node_type in LAYOUT_TYPES:
        for key in FIELDS_LAYOUT:
            if key in node:
                cleaned[key] = node[key]

    # Dimensions et position
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
            relevant = [
                f for f in overridden_fields
                if f in ("characterStyleOverrides", "styleOverrideTable", "characters")
            ]
            if relevant:
                cleaned["overriddenFields"] = relevant

    # Fills, strokes, effects
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

    # Autres propriétés visuelles
    for key in STYLE_FIELDS:
        if key in node:
            cleaned[key] = node[key]

    # Images
    for key in IMAGE_FIELDS:
        if key in node:
            cleaned[key] = node[key]

    # Interactions (clics, navigations, scroll...)   ← AJOUT ICI
    if "interactions" in node and isinstance(node["interactions"], list):
        if node["interactions"]:
            cleaned["interactions"] = node["interactions"]        

    # Récursion sur les enfants
    if "children" in node and isinstance(node["children"], list):
        cleaned_children = [
            _clean_node(child)
            for child in node["children"]
            if isinstance(child, dict)
        ]
        if cleaned_children:
            cleaned["children"] = cleaned_children

    return _prune_empty(cleaned)


# ---------------------------------------------------------------------------
# Nettoyage des props Figma
# ---------------------------------------------------------------------------

def _clean_prop_definitions(prop_defs: dict) -> dict:
    """
    Nettoie les componentPropertyDefinitions d'un COMPONENT ou COMPONENT_SET.

    Pour chaque prop, on garde :
      - type : VARIANT | TEXT | BOOLEAN | INSTANCE_SWAP
      - default : la valeur par défaut
      - options : (VARIANT seulement) la liste des valeurs possibles
    """
    cleaned = {}
    for prop_name, prop_data in prop_defs.items():
        prop_type = prop_data.get("type", "STRING")
        entry = {
            "type": prop_type,
            "default": prop_data.get("defaultValue"),
        }

        # Pour les VARIANT, on garde les options possibles
        if prop_type == "VARIANT" and "variantOptions" in prop_data:
            entry["options"] = prop_data["variantOptions"]

        cleaned[prop_name] = entry

    return _prune_empty(cleaned)


# ---------------------------------------------------------------------------
# Identification du canvas composants
# ---------------------------------------------------------------------------

def _is_components_canvas(name: str) -> bool:
    return any(keyword in name.lower() for keyword in COMPONENTS_CANVAS_KEYWORDS)


# ---------------------------------------------------------------------------
# Scan des composants depuis le canvas
# ---------------------------------------------------------------------------

def _scan_components(
    node: dict,
    components: dict[str, dict],
    component_sets: dict[str, dict],
    inside_set_id: str | None = None,
) -> None:
    """
    Parcourt récursivement le canvas composants et collecte :
      - Les COMPONENT_SET (groupes de variants) avec leurs props
      - Les COMPONENT individuels avec leur définition visuelle

    Le paramètre inside_set_id permet de savoir si on est en train
    de parcourir les enfants d'un COMPONENT_SET. Si c'est le cas,
    les COMPONENT trouvés sont des VARIANTS (pas des standalone).
    On les marque avec _parent_set_id pour le groupement ultérieur.
    """
    node_type = node.get("type", "")
    node_id = node.get("id")

    if node_type == "COMPONENT_SET" and node_id:
        # Un COMPONENT_SET contient les props globales du groupe de variants
        raw_props = node.get("componentPropertyDefinitions", {})
        clean_props = _clean_prop_definitions(raw_props) if raw_props else {}

        component_sets[node_id] = {
            "id": node_id,
            "name": node.get("name"),
            "props": clean_props,
        }

        # Les enfants directs d'un COMPONENT_SET sont ses variants
        # On passe inside_set_id pour les marquer
        for child in node.get("children", []):
            if isinstance(child, dict):
                _scan_components(child, components, component_sets, inside_set_id=node_id)
        return

    if node_type == "COMPONENT" and node_id:
        # Props propres au composant
        raw_props = node.get("componentPropertyDefinitions", {})
        clean_props = _clean_prop_definitions(raw_props) if raw_props else {}

        components[node_id] = {
            "id": node_id,
            "name": node.get("name"),
            "props": clean_props,
            "children": [
                _clean_node(child)
                for child in node.get("children", [])
                if isinstance(child, dict)
            ],
            # Marqueur interne : si ce composant est dans un COMPONENT_SET
            # on le sait directement, sans dépendre du metadata
            "_parent_set_id": inside_set_id,
        }
        return

    # Pour les autres types (FRAME, SECTION, GROUP...) : continuer la récursion
    # On ne propage PAS inside_set_id car seuls les enfants directs
    # d'un COMPONENT_SET sont des variants
    for child in node.get("children", []):
        if isinstance(child, dict):
            _scan_components(child, components, component_sets)


# ---------------------------------------------------------------------------
# Lecture des métadonnées depuis raw["components"]
# ---------------------------------------------------------------------------

def _load_components_metadata(raw: dict) -> dict[str, dict]:
    """
    Lit raw["components"] pour obtenir les métadonnées de chaque composant :
    notamment le componentSetId qui permet de regrouper les variants.

    Exclut les composants remote (venant d'autres fichiers Figma).
    """
    raw_components = raw.get("components", {})

    if not raw_components:
        print("[component_reu] raw['components'] absent ou vide.")
        return {}

    local = {
        comp_id: comp_data
        for comp_id, comp_data in raw_components.items()
        if not comp_data.get("remote", False)
    }

    remote_count = len(raw_components) - len(local)
    print(
        f"[component_reu] {len(local)} composants locaux "
        f"({remote_count} remote exclus)."
    )
    return local


# ---------------------------------------------------------------------------
# Groupement : variants vs standalone
# ---------------------------------------------------------------------------

def _group_components(
    metadata: dict[str, dict],
    scanned_components: dict[str, dict],
    scanned_sets: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """
    Regroupe les composants scannés en :
      - variant_sets : composants qui appartiennent à un COMPONENT_SET
      - standalone : composants indépendants

    Un composant est une variant si :
      1. Il a été scanné à l'intérieur d'un COMPONENT_SET (_parent_set_id)
      2. OU son metadata contient un componentSetId

    La source 1 (scan direct) est prioritaire car elle ne dépend pas
    du metadata qui peut être incomplet.

    Retourne (variant_sets_list, standalone_list)
    """

    # Accumule les variants par set_id
    sets_accumulator: dict[str, dict] = {}
    standalone_ids: list[str] = []

    for comp_id, comp_data in scanned_components.items():
        # Source 1 : marqueur posé pendant le scan
        parent_set_id = comp_data.get("_parent_set_id")

        # Source 2 : metadata
        if parent_set_id is None:
            meta = metadata.get(comp_id)
            if meta:
                parent_set_id = meta.get("componentSetId")

        if not parent_set_id:
            # Pas de set → standalone
            standalone_ids.append(comp_id)
            continue

        # Ce composant est une variant
        if parent_set_id not in sets_accumulator:
            set_info = scanned_sets.get(parent_set_id, {})
            sets_accumulator[parent_set_id] = {
                "kind": "variant_set",
                "component_set_id": parent_set_id,
                "name": set_info.get("name", comp_data.get("name", "Unknown")),
                "props": set_info.get("props", {}),
                "variants": [],
            }

        # Extraire les valeurs de variant depuis le nom Figma
        meta = metadata.get(comp_id, {})
        figma_name = meta.get("name", comp_data["name"])
        variant_values = _parse_variant_values(figma_name)

        sets_accumulator[parent_set_id]["variants"].append({
            "component_id": comp_id,
            "figma_name": figma_name,
            "variant_values": variant_values,
            "definition": {
                "id": comp_data["id"],
                "name": comp_data["name"],
                "props": comp_data.get("props", {}),
                "children": comp_data.get("children", []),
            },
        })

    # Construire la liste standalone
    standalone_list = []
    for comp_id in standalone_ids:
        comp = scanned_components[comp_id]
        standalone_list.append({
            "kind": "standalone",
            "component_id": comp_id,
            "name": comp["name"],
            "props": comp.get("props", {}),
            "definition": {
                "id": comp["id"],
                "name": comp["name"],
                "children": comp.get("children", []),
            },
        })

    variant_sets_list = list(sets_accumulator.values())

    return variant_sets_list, standalone_list


def _parse_variant_values(figma_name: str) -> dict[str, str]:
    """
    Parse le nom Figma d'une variant : "Size=lg, State=hover"
    Retourne : {"Size": "lg", "State": "hover"}

    Si le nom ne contient pas de '=' (pas une variant nommée),
    retourne un dict vide.
    """
    if "=" not in figma_name:
        return {}

    result = {}
    parts = [p.strip() for p in figma_name.split(",")]

    for part in parts:
        if "=" in part:
            prop, value = part.split("=", 1)
            result[prop.strip()] = value.strip()

    return result


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def extract_reusable_components(
    raw_path: Path = RAW_OUTPUT_FILE,
    output_path: Path = COMPONENT_REU_OUTPUT_FILE,
) -> dict:
    """
    Extrait tous les composants réutilisables du JSON Figma.

    Produit un catalogue avec :
      - Les composants standalone (pas de variants)
      - Les variant sets (composants groupés avec props/options)

    Chaque composant inclut sa définition visuelle nettoyée (children)
    et ses props Figma, prêts pour la génération de code.
    """
    print("\n[component_reu] Chargement du fichier raw...")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 1. Lire les métadonnées (pour savoir quel composant → quel set)
    metadata = _load_components_metadata(raw)

    # 2. Scanner le canvas composants
    canvases = raw.get("document", {}).get("children", [])
    scanned_components: dict[str, dict] = {}
    scanned_sets: dict[str, dict] = {}

    for canvas in canvases:
        canvas_name = canvas.get("name", "")
        if _is_components_canvas(canvas_name):
            print(f"[component_reu] Scan du canvas : '{canvas_name}'")
            _scan_components(canvas, scanned_components, scanned_sets)

    print(f"[component_reu] {len(scanned_components)} COMPONENT trouvés")
    print(f"[component_reu] {len(scanned_sets)} COMPONENT_SET trouvés")

    # 3. Grouper en variant sets + standalone
    variant_sets, standalone = _group_components(
        metadata, scanned_components, scanned_sets,
    )

    print(f"[component_reu] {len(variant_sets)} groupes de variants")
    print(f"[component_reu] {len(standalone)} composants standalone")

    # 4. Construire le résultat
    result = {
        "total_standalone": len(standalone),
        "total_variant_sets": len(variant_sets),
        "standalone": standalone,
        "variant_sets": variant_sets,
    }

    # 5. Sauvegarder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"[component_reu] Sauvegardé -> {output_path} ({size_kb:.1f} KB)")

    return result