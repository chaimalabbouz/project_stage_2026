import json
from pathlib import Path
from typing import Any

from config.settings import RAW_OUTPUT_FILE, COMPONENT_REU_OUTPUT_FILE


COMPONENTS_CANVAS_KEYWORDS = [
    "component",
    "style guide",
    "styleguide",
    "design system",
    "library",
]

DESIGN_CANVAS_KEYWORDS = [
    "design",
    "screens",
    "pages",
    "ui",
]

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
# Helpers communs
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


def _clean_effects(effects: Any) -> list[dict]:
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


def _clean_text_style(style: Any) -> dict:
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


def _clean_style_override_table(table: Any) -> dict:
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
# Helpers canvas
# ---------------------------------------------------------------------------

def _is_components_canvas(name: str) -> bool:
    return any(keyword in name.lower() for keyword in COMPONENTS_CANVAS_KEYWORDS)

def _is_design_canvas(name: str) -> bool:
    return any(keyword in name.lower() for keyword in DESIGN_CANVAS_KEYWORDS)

# ---------------------------------------------------------------------------
# Nettoyage d'un node
# ---------------------------------------------------------------------------

def _clean_node(node: dict) -> dict:
    """
    Garde les informations utiles pour générer plus tard un composant React fidèle :
    structure, texte, layout, styles, images.
    """
    node_type = node.get("type", "")

    cleaned = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node_type,
    }

    # Champs génériques utiles
    for key in USEFUL_GENERIC_FIELDS:
        if key in node and key not in {"id", "name", "type"}:
            cleaned[key] = node[key]

    # Layout
    if node_type in LAYOUT_TYPES:
        for key in FIELDS_LAYOUT:
            if key in node:
                cleaned[key] = node[key]

    # Bounds
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

    # Récursion
    if "children" in node and isinstance(node["children"], list):
        cleaned_children = [_clean_node(child) for child in node["children"] if isinstance(child, dict)]
        if cleaned_children:
            cleaned["children"] = cleaned_children

    return _prune_empty(cleaned)


# ---------------------------------------------------------------------------
# Nettoyage déterministe des Props
# ---------------------------------------------------------------------------

def _clean_prop_definitions(prop_defs: dict) -> dict:
    """
    Extrait uniquement le type et la valeur par défaut des props Figma.
    Ignore les métadonnées inutiles.
    """
    cleaned = {}
    for prop_name, prop_data in prop_defs.items():
        cleaned[prop_name] = {
            "type": prop_data.get("type", "STRING"),
            "default": prop_data.get("defaultValue"),
        }
    return _prune_empty(cleaned)


def _clean_prop_overrides(prop_overrides: dict) -> dict:
    """
    Extrait uniquement la valeur réellement appliquée sur une instance.
    """
    cleaned = {}
    for prop_name, prop_data in prop_overrides.items():
        if isinstance(prop_data, dict) and "value" in prop_data:
            cleaned[prop_name] = prop_data["value"]
    return _prune_empty(cleaned)


# ---------------------------------------------------------------------------
# Lecture des métadonnées depuis raw["components"]
# ---------------------------------------------------------------------------

def _load_raw_components_metadata(raw: dict) -> dict[str, dict]:
    raw_components = raw.get("components", {})

    if not raw_components:
        print("[component_reu] raw['components'] absent ou vide -> fallback sur canvas uniquement.")
        return {}

    local_components = {
        comp_id: comp_data
        for comp_id, comp_data in raw_components.items()
        if not comp_data.get("remote", False)
    }

    remote_count = len(raw_components) - len(local_components)
    print(
        f"[component_reu] {len(local_components)} composants locaux dans raw['components'] "
        f"({remote_count} remote exclus)."
    )
    return local_components


# ---------------------------------------------------------------------------
# Parsing multi-props
# ---------------------------------------------------------------------------

def _parse_variant_name(name: str) -> list[dict[str, str]]:
    if "=" not in name:
        return [{"prop": None, "value": name.strip().lower()}]

    results = []
    parts = [p.strip() for p in name.split(",")]

    for part in parts:
        if "=" in part:
            prop, value = part.split("=", 1)
            results.append({
                "prop": prop.strip().lower(),
                "value": value.strip().lower(),
            })
        else:
            results.append({"prop": None, "value": part.strip().lower()})

    return results


# ---------------------------------------------------------------------------
# used_in_frames compact groupé par nom
# ---------------------------------------------------------------------------

def _build_compact_used_in_frames(inst_list: list[dict]) -> dict[str, list[str]]:
    used_in_frames: dict[str, list[str]] = {}
    for item in inst_list:
        frame_name = item["used_in_frame"]["name"]
        frame_id = item["used_in_frame"]["id"]

        if frame_name not in used_in_frames:
            used_in_frames[frame_name] = []

        if frame_id not in used_in_frames[frame_name]:
            used_in_frames[frame_name].append(frame_id)

    return used_in_frames


# ---------------------------------------------------------------------------
# Groupement des variants
# ---------------------------------------------------------------------------

def _group_variants(
    raw_metadata: dict[str, dict],
    scanned_components: dict[str, dict],
    scanned_set_definitions: dict[str, dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    variant_sets: dict[str, dict] = {}
    standalone: dict[str, dict] = {}

    if not raw_metadata:
        return {}, scanned_components

    for comp_id, comp_data in scanned_components.items():
        meta = raw_metadata.get(comp_id)

        if meta is None:
            standalone[comp_id] = comp_data
            continue

        set_id = meta.get("componentSetId")

        if set_id:
            parsed_props = _parse_variant_name(meta["name"])
            valid_props = [p for p in parsed_props if p["prop"]]

            if set_id not in variant_sets:
                react_name = meta["name"].split("=")[0].strip() if "=" in meta["name"] else meta["name"]
                real_props = scanned_set_definitions.get(set_id, {})

                variant_sets[set_id] = {
                    "component_set_id": set_id,
                    "react_name": react_name,
                    "props_from_figma": real_props if real_props else {
                        p["prop"]: {"type": "VARIANT"} for p in valid_props
                    },
                    "variants": [],
                }

            variant_sets[set_id]["variants"].append({
                "component_id": comp_id,
                "figma_name": meta["name"],
                "prop_values": {p["prop"]: p["value"] for p in valid_props} if valid_props else {},
                "definition": {
                    "id": comp_data["id"],
                    "name": comp_data["name"],
                    "children": comp_data.get("children", []),
                },
            })
        else:
            standalone[comp_id] = comp_data

    return variant_sets, standalone


# ---------------------------------------------------------------------------
# Scan composants depuis canvas (inclut les COMPONENT_SET)
# ---------------------------------------------------------------------------

def _scan_components(node: dict, components: dict, set_definitions: dict) -> None:
    node_type = node.get("type", "")
    node_id = node.get("id")

    if node_type == "COMPONENT_SET" and node_id:
        raw_prop_defs = node.get("componentPropertyDefinitions", {})
        if raw_prop_defs:
            set_definitions[node_id] = _clean_prop_definitions(raw_prop_defs)

    elif node_type == "COMPONENT" and node_id:
        raw_prop_defs = node.get("componentPropertyDefinitions", {})
        clean_prop_defs = _clean_prop_definitions(raw_prop_defs) if raw_prop_defs else None

        components[node_id] = {
            "id": node_id,
            "name": node.get("name"),
            "children": [_clean_node(child) for child in node.get("children", []) if isinstance(child, dict)],
            "props_definition": clean_prop_defs,
        }

    for child in node.get("children", []):
        if isinstance(child, dict):
            _scan_components(child, components, set_definitions)


# ---------------------------------------------------------------------------
# Scan instances depuis canvas design
# ---------------------------------------------------------------------------

def _scan_instances(
    node: dict,
    instances: list,
    parent_frame_name: str = "unknown",
    parent_frame_id: str = "unknown",
) -> None:
    node_type = node.get("type", "")

    if node_type == "FRAME" and node.get("name"):
        parent_frame_name = node["name"]
        parent_frame_id = node.get("id", "unknown")

    if node_type == "INSTANCE" and node.get("componentId"):
        raw_overrides = node.get("componentProperties", {})
        clean_overrides = _clean_prop_overrides(raw_overrides) if raw_overrides else None

        instances.append({
            "instance_id": node.get("id"),
            "instance_name": node.get("name"),
            "component_id": node.get("componentId"),
            "used_in_frame": {
                "name": parent_frame_name,
                "id": parent_frame_id,
            },
            "overrides": clean_overrides,
        })

    for child in node.get("children", []):
        if isinstance(child, dict):
            _scan_instances(child, instances, parent_frame_name, parent_frame_id)


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def extract_reusable_components(
    raw_path: Path = RAW_OUTPUT_FILE,
    output_path: Path = COMPONENT_REU_OUTPUT_FILE,
) -> dict:
    print("\n[component_reu] Chargement du fichier raw...")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_metadata = _load_raw_components_metadata(raw)

    canvases = raw.get("document", {}).get("children", [])
    scanned_components: dict[str, dict] = {}
    scanned_set_definitions: dict[str, dict] = {}
    instances: list[dict] = []

    for canvas in canvases:
        canvas_name = canvas.get("name", "")

        if _is_components_canvas(canvas_name):
            print(f"[component_reu] Scan COMPONENTS dans : '{canvas_name}'")
            _scan_components(canvas, scanned_components, scanned_set_definitions)

        elif _is_design_canvas(canvas_name):
            print(f"[component_reu] Scan INSTANCES dans : '{canvas_name}'")
            for child in canvas.get("children", []):
                if isinstance(child, dict):
                   _scan_instances(child, instances)
        







    print(f"[component_reu] {len(scanned_components)} COMPONENT trouvés dans le canvas")
    print(f"[component_reu] {len(instances)} INSTANCE trouvées dans le design")

    variant_sets, standalone_components = _group_variants(
        raw_metadata,
        scanned_components,
        scanned_set_definitions,
    )

    print(f"[component_reu] {len(variant_sets)} groupes de variants détectés")
    print(f"[component_reu] {len(standalone_components)} composants autonomes détectés")

    grouped_instances: dict[str, list] = {}
    for inst in instances:
        cid = inst["component_id"]
        if cid not in grouped_instances:
            grouped_instances[cid] = []
        grouped_instances[cid].append(inst)

    # --- Construction des Standalones ---
    result_standalone = []
    for component_id, comp_def in standalone_components.items():
        inst_list = grouped_instances.get(component_id, [])
        if not inst_list:
            continue

        result_standalone.append({
            "kind": "standalone",
            "component_id": component_id,
            "name": comp_def["name"],
            "total_instances": len(inst_list),
            "used_in_frames": _build_compact_used_in_frames(inst_list),
            "props_definition": comp_def.get("props_definition"),
            "definition": {
                "id": comp_def["id"],
                "name": comp_def["name"],
                "children": comp_def.get("children", []),
            },
            "instances": [
                {
                    "instance_id": item["instance_id"],
                    "instance_name": item["instance_name"],
                    "used_in_frame": item["used_in_frame"],
                    "overrides": item.get("overrides"),
                }
                for item in inst_list
            ],
        })

    # --- Construction des Variants ---
    result_variants = []
    for set_id, variant_set in variant_sets.items():
        all_instances = []
        for variant in variant_set["variants"]:
            all_instances.extend(grouped_instances.get(variant["component_id"], []))

        if not all_instances:
            continue

        result_variants.append({
            "kind": "variant_set",
            "component_set_id": set_id,
            "react_name": variant_set["react_name"],
            "props_from_figma": variant_set.get("props_from_figma"),
            "total_instances": len(all_instances),
            "used_in_frames": _build_compact_used_in_frames(all_instances),
            "variants": variant_set["variants"],
            "instances": [
                {
                    "instance_id": item["instance_id"],
                    "instance_name": item["instance_name"],
                    "used_in_frame": item["used_in_frame"],
                    "overrides": item.get("overrides"),
                }
                for item in all_instances
            ],
        })

    all_components = result_standalone + result_variants
    all_components.sort(key=lambda c: c["total_instances"], reverse=True)

    result = {
        "total_local_components": len(result_standalone),
        "total_variant_sets": len(result_variants),
        "total_instances": sum(c["total_instances"] for c in all_components),
        "components": all_components,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"[component_reu] {len(result_standalone)} standalone + {len(result_variants)} variant sets extraits.")
    print(f"[component_reu] Sauvegardé -> {output_path} ({size_kb:.1f} KB)")

    return result