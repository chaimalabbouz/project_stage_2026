from typing import Any

DEFAULT_NODE_FIELDS = {
    "id",
    "name",
    "type",
    "layoutMode",
    "componentId",
}


def _build_limited_node(
    node: dict[str, Any],
    current_depth: int,
    max_depth: int,
) -> dict[str, Any]:
    limited = {
        key: node[key]
        for key in DEFAULT_NODE_FIELDS
        if key in node
    }

    children = node.get("children", [])
    has_children = isinstance(children, list) and len(children) > 0

    if current_depth < max_depth:
        if has_children:
            limited["children"] = [
                _build_limited_node(child, current_depth + 1, max_depth)
                for child in children
            ]
    else:
        if has_children:
            limited["has_children"] = True
            limited["children_count"] = len(children)

    return limited


def _compute_component_dependencies(
    components: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """
    Pour chaque composant réutilisable, trouve dans quels autres
    composants réutilisables il est utilisé en remontant aux instances racines.

    Logique :
      "I2:955;2:1018" → préfixe "2:955" → instance_id de Header
      → Tab est utilisé dans Header
      → Header depends_on Tab

    Retourne : { "Header": ["Tab", "Active"], "Product": ["Size"], ... }
    """
    # Étape 1 : construire map instance_id → component_name
    # depuis les instances de chaque composant
    instance_id_to_component: dict[str, str] = {}
    for comp in components:
        for instance in comp.get("instances", []):
            iid = instance.get("instance_id", "")
            name = comp.get("name") or comp.get("react_name")
            if iid and name:
                instance_id_to_component[iid] = name

    # Étape 2 : pour chaque composant, chercher si ses used_in_frames
    # ids pointent vers une instance d'un autre composant réutilisable
    # { parent_component_name: set(child_component_names) }
    dependencies: dict[str, set[str]] = {}

    for comp in components:
        child_name = comp.get("name") or comp.get("react_name")
        if not child_name:
            continue

        for frame_name, frame_ids in comp.get("used_in_frames", {}).items():
            for uid in frame_ids:
                if uid.startswith("I"):
                    # "I2:955;2:1018" → root_id = "2:955"
                    root_id = uid.split(";")[0][1:]
                    if root_id in instance_id_to_component:
                        parent_name = instance_id_to_component[root_id]
                        if parent_name != child_name:
                            dependencies.setdefault(parent_name, set())
                            dependencies[parent_name].add(child_name)

    return {k: sorted(v) for k, v in dependencies.items()}


def _lighten_reusable_components(
    reusable_components_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Produit un résumé léger des composants pour le planning.
    On ne garde que ce dont le LLM a besoin pour :
      - identifier les composants partagés entre pages
      - détecter les dépendances
      - établir l'ordre de génération

    On exclut volontairement :
      - definition (structure interne complète)
      - instances (liste détaillée des instances)
      - props_from_figma / props_definition détaillées
      - absoluteBoundingBox, fills, styles, tokens
    """
    result = []

    for comp in reusable_components_data.get("components", []):
        kind = comp.get("kind")
        name = comp.get("name") or comp.get("react_name")

        if (
            comp.get("component_set_id") is None
            and comp.get("component_id") is None
            and name is None
        ):
            continue

        used_in_frames = [
            {"name": frame_name, "ids": frame_ids}
            for frame_name, frame_ids in comp.get("used_in_frames", {}).items()
        ]

        summary = {
            "kind": kind,
            "name": name,
            "total_instances": comp.get("total_instances", 0),
            "used_in_frames": used_in_frames,
        }

        if kind == "variant_set":
            summary["component_set_id"] = comp.get("component_set_id")
            summary["variants"] = [
                v.get("prop_values")
                for v in comp.get("variants", [])
                if v.get("prop_values")
            ]

        elif kind == "standalone":
            summary["component_id"] = comp.get("component_id")

        result.append(summary)

    result.sort(key=lambda x: x.get("total_instances", 0), reverse=True)
    return result


def build_planner_payload(
    cleaned_json: dict[str, Any],
    reusable_components_data: dict[str, Any],
    max_depth: int = 4,
) -> dict[str, Any]:
    """
    Construit le payload envoyé au LLM pour l'étape de planning uniquement.

    Contient :
      - figma_tree             : arbre Figma limité à max_depth niveaux
      - reusable_components    : résumé léger des composants
      - component_dependencies : dépendances pré-calculées entre composants
                                 { "Header": ["Tab", "Active"], ... }

    Exclu volontairement (réservé à l'étape de génération) :
      - definition (structure JSX interne complète)
      - instances (liste détaillée des usages)
      - props_from_figma / props_definition détaillées
      - styles, fills, tokens, absoluteBoundingBox
      - layout_strategy, props
    """
    canvases = cleaned_json.get("document", {}).get("children", [])

    limited_canvases = [
        _build_limited_node(canvas, current_depth=1, max_depth=max_depth)
        for canvas in canvases
    ]

    reusable_components = _lighten_reusable_components(reusable_components_data)

    component_dependencies = _compute_component_dependencies(
        reusable_components_data.get("components", [])
    )

    payload = {
        "figma_tree": {
            "max_depth": max_depth,
            "total_canvases": len(limited_canvases),
            "document": {
                "children": limited_canvases
            },
        },
        "reusable_components": reusable_components,
        "component_dependencies": component_dependencies,
    }

    return payload