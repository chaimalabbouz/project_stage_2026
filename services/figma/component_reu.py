import json
from pathlib import Path
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

FIELDS_TO_KEEP = {
    "id",
    "name",
    "type",
    "children",
    "layoutMode",
    "componentId",
    "characters",
}


def _is_components_canvas(name: str) -> bool:
    return any(keyword in name.lower() for keyword in COMPONENTS_CANVAS_KEYWORDS)


def _is_design_canvas(name: str) -> bool:
    return any(keyword in name.lower() for keyword in DESIGN_CANVAS_KEYWORDS)


def _clean_node(node: dict) -> dict:
    """
    Garde uniquement les champs essentiels d'un node, récursivement.
    """
    cleaned = {key: node[key] for key in FIELDS_TO_KEEP if key in node}

    if "children" in node and isinstance(node["children"], list):
        cleaned["children"] = [_clean_node(child) for child in node["children"]]

    return cleaned


def _scan_components(node: dict, components: dict) -> None:
    """
    Parcourt récursivement un canvas/components tree
    et récupère les définitions des COMPONENT locaux.
    """
    if node.get("type") == "COMPONENT" and node.get("id"):
        components[node["id"]] = {
            "id": node["id"],
            "name": node.get("name"),
            "children": [_clean_node(child) for child in node.get("children", [])],
        }

    for child in node.get("children", []):
        _scan_components(child, components)


def _scan_instances(node: dict, instances: list, parent_frame: str = "unknown") -> None:
    """
    Parcourt récursivement un arbre de design
    et récupère toutes les INSTANCE avec leur componentId.
    """
    node_type = node.get("type", "")

    if node_type == "FRAME" and node.get("name"):
        parent_frame = node["name"]

    if node_type == "INSTANCE" and node.get("componentId"):
        instances.append({
            "instance_id": node.get("id"),
            "instance_name": node.get("name"),
            "component_id": node.get("componentId"),
            "used_in_frame": parent_frame,
        })

    for child in node.get("children", []):
        _scan_instances(child, instances, parent_frame)


def extract_reusable_components(
    raw_path: Path = RAW_OUTPUT_FILE,
    output_path: Path = COMPONENT_REU_OUTPUT_FILE,
) -> dict:
    """
    Extrait les composants réutilisables locaux :
    - détecte les canvases de composants
    - détecte les canvases de design
    - collecte les COMPONENT
    - collecte les INSTANCE
    - lie les instances à leurs définitions locales
    - sauvegarde le résultat
    """
    print("\n[component_reu] Chargement du fichier raw...")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    canvases = raw.get("document", {}).get("children", [])
    components = {}
    instances = []

    for canvas in canvases:
        canvas_name = canvas.get("name", "")

        if _is_components_canvas(canvas_name):
            print(f"[component_reu] Scan COMPONENTS dans : '{canvas_name}'")
            _scan_components(canvas, components)

        elif _is_design_canvas(canvas_name):
            print(f"[component_reu] Scan INSTANCES dans : '{canvas_name}'")
            for child in canvas.get("children", []):
                _scan_instances(child, instances)

    print(f"[component_reu] {len(components)} COMPONENT trouvés")
    print(f"[component_reu] {len(instances)} INSTANCE trouvées")

    grouped_instances = {}
    for inst in instances:
        component_id = inst["component_id"]
        if component_id not in grouped_instances:
            grouped_instances[component_id] = []
        grouped_instances[component_id].append(inst)

    result_components = []
    for component_id, inst_list in grouped_instances.items():
        comp_def = components.get(component_id)
        if comp_def is None:
            continue

        used_in_frames = sorted({item["used_in_frame"] for item in inst_list})

        result_components.append({
            "component_id": component_id,
            "name": comp_def["name"],
            "total_instances": len(inst_list),
            "used_in_frames": used_in_frames,
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
                }
                for item in inst_list
            ],
        })

    result_components.sort(key=lambda comp: comp["total_instances"], reverse=True)

    result = {
        "total_local_components": len(result_components),
        "total_instances": sum(comp["total_instances"] for comp in result_components),
        "components": result_components,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"[component_reu] {len(result_components)} composants locaux extraits.")
    print(f"[component_reu] Sauvegardé -> {output_path} ({size_kb:.1f} KB)")

    return result