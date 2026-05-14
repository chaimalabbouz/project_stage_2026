"""
section_extractor.py
====================
Parcourt chaque page Figma et produit sections.json, qui contient :

  Pour chaque page :
    - page_styles : styles minimaux de la page (size, background)
    - ordered_children : les enfants dans l ordre visuel, chacun étant :
        * soit une INSTANCE d un composant réutilisable
          -> placeholder avec component_id + props_values (matching EXACT)
        * soit une SECTION libre (FRAME non réutilisable)
          -> arbre nettoyé avec STYLES à chaque nœud significatif

Ce fichier garantit :
  - Matching EXACT des overrides par figma_name (pas de fuzzy matching)
  - Warnings explicites si un override ne matche aucune prop
  - Perf : un seul parsing du raw.json via index node_id -> node
  - Styles des éléments libres extraits pour fidélité visuelle max

Les fonctions de style sont importées depuis architect.py pour garantir
la cohérence entre composants réutilisables et éléments libres.
"""

import json
from pathlib import Path
from config.settings import (
    TREE_OUTPUT_FILE,
    SECTIONS_OUTPUT_FILE,
    ARCHITECTURE_FILE,
    MINIMAL_OUTPUT_FILE
)

# Réutilisation des fonctions de styles déjà écrites dans architect.py
from architect.architecte import (
    _extract_size,
    _extract_layout_style,
    _extract_common_visual,
    _extract_text_style,
    _should_style_node,
    _node_has_image_fill,
)


# Profondeur max de descente dans la hiérarchie (garde-fou)
MAX_DEPTH = 8
ALLOWED_OVERLAY_TYPES = {"FRAME", "GROUP", "INSTANCE"}
IGNORED_OVERLAY_TYPES = {"TEXT", "VECTOR", "LINE", "BOOLEAN_OPERATION", "ELLIPSE"}

MIN_OVERLAY_WIDTH = 250
MIN_OVERLAY_HEIGHT = 120
MIN_OVERLAP_AREA = 10000


# ═══════════════════════════════════════════════════════════════
# Index du raw.json pour lookup O(1)
# ═══════════════════════════════════════════════════════════════

def _build_raw_index(raw_path: Path = MINIMAL_OUTPUT_FILE) -> dict[str, dict]:
    """Charge raw.json une seule fois et construit un index {node_id: node}.
    Évite de re-parser le fichier pour chaque enfant.
    """
    print(f"[sections_extractor] Construction de l'index raw...")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    index: dict[str, dict] = {}

    def _walk(node):
        if not isinstance(node, dict):
            return
        node_id = node.get("id")
        if node_id:
            index[node_id] = node
        for child in node.get("children", []):
            _walk(child)

    for canvas in raw.get("document", {}).get("children", []):
        _walk(canvas)

    print(f"[sections_extractor] Index raw : {len(index)} nœuds indexés.")
    return index


def _find_node(raw_index: dict[str, dict], node_id: str) -> dict | None:
    """Lookup O(1) dans l'index."""
    return raw_index.get(node_id)

# ═══════════════════════════════════════════════════════════════
# fonctione necessaire pour le grid 
# ═══════════════════════════════════════════════════════════════

def _detect_grid_columns(children: list[dict]) -> int:
    rows = {}

    for child in children:
        if not isinstance(child, dict):
            continue

        bbox = child.get("_bbox")
        if not bbox:
            continue

        y = round(bbox.get("y", 0), 1)

        # Regrouper les éléments par ligne (tolérance)
        found_row = None
        for key in rows:
            if abs(key - y) < 5:
                found_row = key
                break

        if found_row is None:
            rows[y] = [child]
        else:
            rows[found_row].append(child)

    if not rows:
        return 1

    # Première ligne (plus petit y)
    first_row = sorted(rows.keys())[0]
    return len(rows[first_row])
# ═══════════════════════════════════════════════════════════════
# Chargement et indexation de architecture.json
# ═══════════════════════════════════════════════════════════════

def _load_architecture_index() -> dict[str, dict]:
    """Charge architecture.json et construit un index {component_id: entry}.
    Pour chaque entrée, on indexe sur :
      - le component_id principal
      - tous les variant_component_ids
      - le component_set_id si présent
    Ainsi le lookup marche que l'instance pointe vers le set ou une variante.
    """
    try:
        with open(ARCHITECTURE_FILE, "r", encoding="utf-8") as f:
            arch_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[sections_extractor] ERREUR : architecture.json illisible : {e}")
        return {}

    index: dict[str, dict] = {}
    for comp in arch_data.get("components", []):
        main_id = comp.get("component_id")
        if main_id:
            index[main_id] = comp
        for vid in comp.get("variant_component_ids", []):
            index[vid] = comp
        set_id = comp.get("component_set_id")
        if set_id:
            index[set_id] = comp

    print(f"[sections_extractor] Architecture : {len(index)} component_ids indexés.")
    return index


def _build_props_index(arch_entry: dict) -> dict[str, str]:
    """Pour une entrée d'architecture, construit {figma_name: react_name}.
    Permet le matching EXACT des overrides vers les props React.
    """
    props_index: dict[str, str] = {}
    architecture = arch_entry.get("architecture", {})
    for prop in architecture.get("props", []):
        figma_name = prop.get("figma_name")
        react_name = prop.get("name")
        if figma_name and react_name:
            props_index[figma_name] = react_name
    return props_index


# ═══════════════════════════════════════════════════════════════
# Collecte des overrides d'une INSTANCE
# ═══════════════════════════════════════════════════════════════
def _collect_text_overrides(instance_node: dict) -> list[dict]:
    overrides = []

    def _scan(node):
        if not isinstance(node, dict):
            return

        if node.get("type") == "TEXT" and "characters" in node:
            figma_name = node.get("name", "")
            if figma_name:
                overrides.append({
                    "kind": "text",
                    "figma_name": figma_name,
                    "value": node["characters"],
                })

        for child in node.get("children", []):
            _scan(child)

    _scan(instance_node)
    return overrides


def _collect_image_overrides(instance_node: dict) -> list[dict]:
    overrides = []

    def _scan(node):
        if not isinstance(node, dict):
            return

        has_img, image_ref = _node_has_image_fill(node)
        if has_img and image_ref:
            figma_name = node.get("name", "")
            overrides.append({
                "kind": "image",
                "figma_name": figma_name,
                "value": image_ref,
            })

        for child in node.get("children", []):
            _scan(child)

    _scan(instance_node)
    return overrides


def _collect_variant_overrides(instance_node: dict) -> list[dict]:
    overrides = []
    comp_props = instance_node.get("componentProperties", {})

    if not isinstance(comp_props, dict):
        return overrides

    for key, val in comp_props.items():
        if isinstance(val, dict):
            value = val.get("value", val)
        else:
            value = val

        overrides.append({
            "kind": "variant",
            "figma_name": key,
            "value": value,
        })

    return overrides


def _collect_all_overrides(instance_node: dict) -> list[dict]:
    overrides = []
    overrides.extend(_collect_text_overrides(instance_node))
    overrides.extend(_collect_image_overrides(instance_node))
    overrides.extend(_collect_variant_overrides(instance_node))
    return overrides












# ═══════════════════════════════════════════════════════════════
# Matching EXACT overrides -> props React
# ═══════════════════════════════════════════════════════════════

def _match_overrides_to_props(
    overrides: list[dict],
    arch_entry: dict,
    component_name: str = "",
) -> dict[str, str]:
    props_values: dict[str, str] = {}

    architecture = arch_entry.get("architecture", {})
    props = architecture.get("props", [])

    props_index = {}
    for prop in props:
        figma_name = prop.get("figma_name")
        react_name = prop.get("name")
        if figma_name and react_name:
            props_index[figma_name] = prop

    used_props = set()
    unmatched_text = []
    unmatched_image = []
    unmatched_variant = []

    # 1. Matching exact par figma_name
    for override in overrides:
        kind = override.get("kind")
        figma_name = override.get("figma_name")
        value = override.get("value")

        prop = props_index.get(figma_name)

        if prop:
            react_name = prop.get("name")
            props_values[react_name] = value
            used_props.add(react_name)
        else:
            if kind == "text":
                unmatched_text.append(override)
            elif kind == "image":
                unmatched_image.append(override)
            else:
                unmatched_variant.append(override)

    # 2. Fallback TEXT par ordre
    text_props = [
        p for p in props
        if p.get("source") == "text" and p.get("name") not in used_props
    ]

    for override, prop in zip(unmatched_text, text_props):
        react_name = prop.get("name")
        if react_name:
            props_values[react_name] = override.get("value")
            used_props.add(react_name)

    # 3. Fallback IMAGE par ordre
    image_props = [
        p for p in props
        if p.get("source") == "image" and p.get("name") not in used_props
    ]

    for override, prop in zip(unmatched_image, image_props):
        react_name = prop.get("name")
        if react_name:
            props_values[react_name] = override.get("value")
            used_props.add(react_name)

    # 4. Warnings seulement pour ce qui reste vraiment non mappé
    remaining = []

    if len(unmatched_text) > len(text_props):
        remaining.extend(o.get("figma_name") for o in unmatched_text[len(text_props):])

    if len(unmatched_image) > len(image_props):
        remaining.extend(o.get("figma_name") for o in unmatched_image[len(image_props):])

    remaining.extend(o.get("figma_name") for o in unmatched_variant)

    if remaining:
        print(
            f"  [WARN] {component_name}: {len(remaining)} override(s) "
            f"sans prop correspondante : {remaining}"
        )

    return props_values


# ═══════════════════════════════════════════════════════════════
# Résolution du nom React d'un composant
# ═══════════════════════════════════════════════════════════════

def _resolve_react_name(
    component_id: str,
    architecture_index: dict[str, dict],
    fallback_figma_name: str,
) -> str:
    """Retourne le nom React du composant depuis architecture.json.
    Si pas trouvé : WARNING + fallback sur le nom Figma.
    """
    arch = architecture_index.get(component_id)
    if arch:
        return arch.get("name", fallback_figma_name)

    print(f"  [WARN] component_id {component_id} absent de architecture.json, "
          f"fallback sur '{fallback_figma_name}'")
    return fallback_figma_name


# ═══════════════════════════════════════════════════════════════
# Tri visuel des enfants (layout-aware)
# ═══════════════════════════════════════════════════════════════

def _get_node_position(node: dict) -> tuple[float, float]:
    """Retourne (y, x) depuis absoluteBoundingBox."""
    bbox = node.get("absoluteBoundingBox", {})
    return (
        bbox.get("y", float("inf")),
        bbox.get("x", float("inf")),
    )


def _sort_children_by_visual_position(
    children: list[dict],
    raw_index: dict[str, dict],
    parent_layout_mode: str | None = None,
) -> list[dict]:
    """Trie les enfants selon leur position visuelle.
    - Si parent HORIZONTAL : tri par X puis Y
    - Sinon (VERTICAL, NONE, inconnu) : tri par Y puis X
    X en secondaire départage les éléments alignés sur la même ligne.
    """
    def _sort_key(child_tree_node):
        child_id = child_tree_node.get("id")
        raw_node = raw_index.get(child_id)
        if not raw_node:
            return (float("inf"), float("inf"))

        y, x = _get_node_position(raw_node)
        if parent_layout_mode == "HORIZONTAL":
            return (x, y)
        else:
            return (y, x)

    return sorted(children, key=_sort_key)


# ═══════════════════════════════════════════════════════════════
# Extraction des styles pour un nœud libre (non-instance)
# ═══════════════════════════════════════════════════════════════

def _extract_node_styles_for_section(node: dict) -> dict:
    """Retourne un dict de styles complet pour un nœud libre.
    Réutilise les fonctions de architect.py pour garantir la cohérence.

    - Pour TEXT : typo + color + size
    - Pour les autres : size + layout + visuel (fills, radius, borders, effects)
    - Si le parent n'a PAS de layoutMode : ajouter les coordonnées absolues
    """
    ntype = node.get("type", "")
    styles = {}

    if ntype == "TEXT":
        styles.update(_extract_text_style(node))
        styles.update(_extract_size(node))
        return styles

    # Size
    styles.update(_extract_size(node))

    # Layout (flex)
    layout = _extract_layout_style(node)
    if layout:
        styles["layout"] = layout

    # Visuels (fills, radius, borders, effects, opacity)
    styles.update(_extract_common_visual(node))

    return styles

##########################



def _extract_interaction(node: dict) -> list | None:
    """Extrait toutes les interactions du nœud.
    
    Garde TOUS les triggers et actions (pas de filtrage).
    Préserve destinationId pour la résolution de routes plus tard.
    Format cohérent avec architect.py.
    """
    interactions = node.get("interactions") or node.get("reactions") or []
    
    if not isinstance(interactions, list) or not interactions:
        return None
    
    simplified = []
    for inter in interactions:
        if not isinstance(inter, dict):
            continue
        
        trigger = inter.get("trigger", {})
        trigger_type = trigger.get("type") if isinstance(trigger, dict) else None
        if not trigger_type:
            continue
        
        actions = inter.get("actions", [])
        if not isinstance(actions, list):
            continue
        
        simplified_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            
            entry = {"type": action.get("type")}
            
            # ✅ Préserver destinationId (clé pour la résolution de routes)
            if "destinationId" in action:
                entry["destinationId"] = action["destinationId"]
            
            if "navigation" in action:
                entry["navigation"] = action["navigation"]
            
            simplified_actions.append(entry)
        
        if simplified_actions:
            simplified.append({
                "trigger": trigger_type,
                "actions": simplified_actions,
            })
    
    return simplified if simplified else None

def _collect_descendant_interactions(
    instance_node: dict,
    interactions_index: dict[str, dict],
) -> dict:
    """Scanne récursivement les enfants d'une INSTANCE et collecte 
    leurs interactions par figma_name.
    
    Retourne : {figma_name: [interactions...]}
    """
    result = {}
    
    def _scan(node):
        if not isinstance(node, dict):
            return
        
        node_id = node.get("id")
        node_inter = interactions_index.get(node_id)
        
        if node_inter:
            figma_name = node.get("name", "")
            if figma_name and figma_name not in result:
                result[figma_name] = node_inter
        
        for child in node.get("children", []):
            _scan(child)
    
    # Scanner UNIQUEMENT les enfants (pas l'instance elle-même)
    for child in instance_node.get("children", []):
        _scan(child)
    
    return result



def _build_interactions_index(raw_index: dict[str, dict]) -> dict[str, dict]:
    interactions_index = {}

    for node_id, node in raw_index.items():
        interaction = _extract_interaction(node)
        if interaction:
            interactions_index[node_id] = interaction
            print(
                f"[interaction] source={node_id} "
                f"name={node.get('name')} -> {interaction}"
            )

    print(f"[sections_extractor] Interactions détectées : {len(interactions_index)}")
    return interactions_index    



#####################
# ═══════════════════════════════════════════════════════════════
# Nettoyage récursif d'une section libre
# ═══════════════════════════════════════════════════════════════

# Champs "utiles" à garder en plus des styles (qui sont ajoutés à part)
BASIC_FIELDS = {"id", "name", "type", "componentId"}


def _clean_node_recursive(
    node: dict,
    architecture_index: dict[str, dict],
    raw_index: dict[str, dict],
    interactions_index: dict[str, dict],
    instances_found: list[dict],
    depth: int = 0,
) -> dict:
    """Nettoie un nœud récursivement.
    - Si c'est une INSTANCE réutilisable : retourne un placeholder avec
      props_values (matching exact), SANS styles (ils sont dans architecture.json)
    - Sinon : retourne le nœud nettoyé avec STYLES + enfants nettoyés
    """
    node_type = node.get("type", "")
    component_id = node.get("componentId")

    # Récupérer interaction éventuelle du node
    interaction = interactions_index.get(node.get("id"))

    # ─── Cas 1 : instance de composant réutilisable ───
    if node_type == "INSTANCE" and component_id in architecture_index:
        arch_entry = architecture_index[component_id]
        react_name = arch_entry.get("name", node.get("name", "Component"))
        overrides = _collect_all_overrides(node)
        props_values = _match_overrides_to_props(overrides, arch_entry, react_name)

        # ✅ NOUVEAU : collecter les interactions des enfants de l'instance
        child_interactions = _collect_descendant_interactions(node, interactions_index)

        # Garder SEULEMENT les styles de positionnement et taille
        full_styles = _extract_node_styles_for_section(node)
        instance_styles = {}
        for key in ("width", "height", "_positioning", "_position"):
            if key in full_styles:
                instance_styles[key] = full_styles[key]

        if "layout" in full_styles:
            layout = full_styles["layout"]
            kept = {}
            for k in (
                "layoutSizingHorizontal",
                "layoutSizingVertical",
                "layoutGrow",
                "layoutAlign",
            ):
                if k in layout:
                    kept[k] = layout[k]
            if kept:
                instance_styles["layout"] = kept

        instance_info = {
            "id": node.get("id"),
            "name": node.get("name"),
            "component_id": component_id,
            "react_component_name": react_name,
            "props_values": props_values,
        }

        if interaction:
            instance_info["interaction"] = interaction

        # ✅ NOUVEAU
        if child_interactions:
            instance_info["child_interactions"] = child_interactions

        instances_found.append(instance_info)

        placeholder = {
            "type": "__COMPONENT_PLACEHOLDER__",
            "react_component_name": react_name,
            "id": node.get("id"),
            "component_id": component_id,
            "props_values": props_values,
        }

        if interaction:
            placeholder["interaction"] = interaction

        # ✅ NOUVEAU
        if child_interactions:
            placeholder["child_interactions"] = child_interactions

        if instance_styles:
            placeholder["styles"] = instance_styles

        bbox = node.get("absoluteBoundingBox")
        if not bbox and node.get("id"):
            raw_node = raw_index.get(node.get("id"))
            if raw_node:
                bbox = raw_node.get("absoluteBoundingBox")

        if isinstance(bbox, dict):
            placeholder["_bbox"] = {
                "x": bbox.get("x", 0),
                "y": bbox.get("y", 0),
                "width": bbox.get("width", 0),
                "height": bbox.get("height", 0),
            }

        return placeholder

    # ─── Cas 2 : nœud libre ───
    cleaned = {k: node[k] for k in BASIC_FIELDS if k in node}

    if interaction:
        cleaned["interaction"] = interaction

    # Ajouter characters si c'est un TEXT
    if node_type == "TEXT" and "characters" in node:
        cleaned["characters"] = node["characters"]

    # Ajouter les styles
    if _should_style_node(node):
        styles = _extract_node_styles_for_section(node)
        if styles:
            cleaned["styles"] = styles

    # Ajouter les coordonnées absolues
    bbox = node.get("absoluteBoundingBox")
    if not bbox and node.get("id"):
        raw_node = raw_index.get(node.get("id"))
        if raw_node:
            bbox = raw_node.get("absoluteBoundingBox")

    if not bbox and node_type in ("FRAME", "GROUP", "INSTANCE"):
        print(
            f"    [WARN BBOX] '{node.get('name', '?')}' "
            f"(id={node.get('id', '?')}) n'a PAS de absoluteBoundingBox dans le raw"
        )

    if isinstance(bbox, dict):
        cleaned["_bbox"] = {
            "x": bbox.get("x", 0),
            "y": bbox.get("y", 0),
            "width": bbox.get("width", 0),
            "height": bbox.get("height", 0),
        }

    # Récursion sur les enfants
    if depth < MAX_DEPTH and "children" in node:
        cleaned_children = []
        for child in node["children"]:
            if isinstance(child, dict):
                cleaned_child = _clean_node_recursive(
                    child,
                    architecture_index,
                    raw_index,
                    interactions_index,
                    instances_found,
                    depth + 1,
                )
                cleaned_children.append(cleaned_child)

        if cleaned_children:
            cleaned["children"] = cleaned_children

    return cleaned

def _flatten_useless_wrappers(node: dict) -> dict | None:
    """Supprime les FRAME intermédiaires inutiles (pas de style, pas de contenu).
    - Si un FRAME n'a pas de styles et a un seul enfant → remplacé par l'enfant
    - Si un FRAME n'a pas de styles et zéro enfant → supprimé (retourne None)
    - Appliqué récursivement de bas en haut.
    """
    if not isinstance(node, dict):
        return node

    # Ne jamais toucher aux placeholders
    if node.get("type") == "__COMPONENT_PLACEHOLDER__":
        return node
    if node.get("interaction"):
        return node

    # D'abord, récursion sur les enfants
    if "children" in node and isinstance(node["children"], list):
        cleaned_children = []
        for child in node["children"]:
            result = _flatten_useless_wrappers(child)
            if result is not None:
                cleaned_children.append(result)
        node["children"] = cleaned_children

    # Maintenant, vérifier si CE nœud est un wrapper inutile
    node_type = node.get("type", "")

    # Seuls les FRAME/GROUP sans style sont candidats à l'aplatissement
    if node_type not in ("FRAME", "GROUP"):
        return node

    # A-t-il des styles ?
    has_styles = bool(node.get("styles"))

    # A-t-il du contenu propre ?
    has_content = bool(node.get("characters"))

    if has_styles or has_content:
        return node

    children = node.get("children", [])

    # Zéro enfant et pas de style → inutile, supprimer
    if len(children) == 0:
        return None

    # Un seul enfant et pas de style → remplacer par l'enfant
    if len(children) == 1:
        return children[0]

    # Plusieurs enfants mais pas de style → garder comme conteneur
    return node

def _overlap_area(a: dict, b: dict) -> float:
    ax1 = a.get("x", 0)
    ay1 = a.get("y", 0)
    ax2 = ax1 + a.get("width", 0)
    ay2 = ay1 + a.get("height", 0)

    bx1 = b.get("x", 0)
    by1 = b.get("y", 0)
    bx2 = bx1 + b.get("width", 0)
    by2 = by1 + b.get("height", 0)

    overlap_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    overlap_h = max(0, min(ay2, by2) - max(ay1, by1))

    return overlap_w * overlap_h


def _is_overlay_candidate(node: dict) -> bool:
    node_type = node.get("type", "")
    bbox = node.get("_bbox")

    if node_type in IGNORED_OVERLAY_TYPES:
        return False

    if node_type not in ALLOWED_OVERLAY_TYPES:
        return False

    if not isinstance(bbox, dict):
        return False

    if bbox.get("width", 0) < MIN_OVERLAY_WIDTH:
        return False

    if bbox.get("height", 0) < MIN_OVERLAY_HEIGHT:
        return False

    return True

def _compute_children_union_height(children: list[dict], parent_bbox: dict) -> float:
    """Calcule la hauteur nécessaire du parent pour contenir ses enfants absolute."""
    if not isinstance(parent_bbox, dict):
        return 0

    parent_y = parent_bbox.get("y", 0)
    max_bottom = 0

    for child in children:
        if not isinstance(child, dict):
            continue

        bbox = child.get("_bbox")
        if not isinstance(bbox, dict):
            continue

        child_bottom = bbox.get("y", 0) + bbox.get("height", 0)
        relative_bottom = child_bottom - parent_y
        max_bottom = max(max_bottom, relative_bottom)

    return round(max_bottom, 1)

def _mark_sibling_overlays(node: dict) -> None:
    children = node.get("children", [])
    if len(children) < 2:
        return

    parent_bbox = node.get("_bbox")
    if not isinstance(parent_bbox, dict):
        return

    parent_x = parent_bbox.get("x", 0)
    parent_y = parent_bbox.get("y", 0)

    candidates = [
        child for child in children
        if isinstance(child, dict) and _is_overlay_candidate(child)
    ]

    for i in range(len(candidates)):
        a = candidates[i]
        bbox_a = a.get("_bbox")

        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            bbox_b = b.get("_bbox")

            area = _overlap_area(bbox_a, bbox_b)

            if area >= MIN_OVERLAP_AREA:
                node.setdefault("styles", {})
                node["styles"]["_positioning"] = "absolute"

                needed_height = _compute_children_union_height(children, parent_bbox)
                if needed_height > 0:
                    node["styles"]["height"] = needed_height

                b.setdefault("styles", {})
                b["styles"]["_position"] = {
                    "top": round(bbox_b.get("y", 0) - parent_y, 1),
                    "left": round(bbox_b.get("x", 0) - parent_x, 1),
                }
                b["styles"]["zIndex"] = j + 10



def _inject_absolute_positions(node: dict) -> dict:
    if not isinstance(node, dict):
        return node

    styles = node.get("styles", {})
    layout = styles.get("layout", {})
    has_layout_mode = bool(layout.get("layoutMode"))

    children = node.get("children", [])

    # Détecter les overlays avant de supprimer les _bbox
    _mark_sibling_overlays(node)

    # Détection GRID seulement si le parent n'a pas déjà Auto Layout
    if children and not has_layout_mode:
        cols = _detect_grid_columns(children)

        if cols > 1:
            node.setdefault("styles", {})
            node["styles"].setdefault("layout", {})
            node["styles"]["layout"]["layoutMode"] = "GRID"
            node["styles"]["layout"]["gridColumns"] = cols

            # IMPORTANT : si on détecte GRID, on ne force pas les enfants en absolute
            has_layout_mode = True

    # Cas 1 : parent avec Auto Layout ou GRID → ne rien faire
    if has_layout_mode:
        pass

    # Cas 2 : parent sans Auto Layout / sans GRID → enfants en absolute
    elif children:
        parent_bbox = node.get("_bbox", {})

        if not parent_bbox:
            print(
                f"    [WARN] '{node.get('name', '?')}' "
                f"(id={node.get('id', '?')}) sans _bbox"
            )
        else:
            parent_x = parent_bbox.get("x", 0)
            parent_y = parent_bbox.get("y", 0)

            node.setdefault("styles", {})
            node["styles"]["_positioning"] = "absolute"

            for child in children:
                if not isinstance(child, dict):
                    continue

                child_bbox = child.get("_bbox", {})
                child_styles = child.get("styles", {})

                if child_bbox and "_position" not in child_styles:
                    child.setdefault("styles", {})
                    child["styles"]["_position"] = {
                        "top": round(child_bbox.get("y", 0) - parent_y, 1),
                        "left": round(child_bbox.get("x", 0) - parent_x, 1),
                    }

    # Récursion après traitement du parent
    if "children" in node and isinstance(node["children"], list):
        node["children"] = [
            _inject_absolute_positions(child)
            for child in node["children"]
            if isinstance(child, dict)
        ]

    # Nettoyer les bbox seulement à la toute fin
    for child in node.get("children", []):
        if isinstance(child, dict):
            child.pop("_bbox", None)

    node.pop("_bbox", None)

    return node
def _detect_layout_direction(node: dict) -> str:
    """Détecte si les enfants sont alignés horizontalement ou verticalement."""
    children = node.get("children", [])
    if len(children) < 2:
        return "VERTICAL"
    
    positions = []
    for child in children:
        styles = child.get("styles", {})
        pos = styles.get("_position")
        bbox = child.get("_bbox", {})
        
        if pos:
            positions.append((pos.get("left", 0), pos.get("top", 0)))
        elif bbox:
            positions.append((bbox.get("x", 0), bbox.get("y", 0)))
    
    if len(positions) < 2:
        return "VERTICAL"
    
    first_x, first_y = positions[0]
    x_var = 0
    y_var = 0
    
    for x, y in positions[1:]:
        x_var += abs(x - first_x)
        y_var += abs(y - first_y)
    
    return "HORIZONTAL" if x_var > y_var else "VERTICAL"




# ═══════════════════════════════════════════════════════════════
# Styles minimalistes pour la page elle-même
# ═══════════════════════════════════════════════════════════════

def _extract_page_styles(page_node: dict) -> dict:
    """Styles minimaux de la page : size + background.
    Ce sont les styles du canvas/frame racine de la page.
    """
    styles = {}

    # Size depuis absoluteBoundingBox si dispo
    bbox = page_node.get("absoluteBoundingBox")
    if isinstance(bbox, dict):
        if "width" in bbox:
            styles["width"] = bbox["width"]
        if "height" in bbox:
            styles["height"] = bbox["height"]

    # Background color si présent
    bg = page_node.get("backgroundColor")
    if isinstance(bg, dict):
        r = int(round(bg.get("r", 0) * 255))
        g = int(round(bg.get("g", 0) * 255))
        b = int(round(bg.get("b", 0) * 255))
        styles["backgroundColor"] = f"#{r:02x}{g:02x}{b:02x}"

    # Fills éventuels (plus complets que backgroundColor seul)
    fills = page_node.get("fills")
    if isinstance(fills, list) and fills:
        # On utilise _extract_common_visual pour récupérer fills proprement
        visual = _extract_common_visual(page_node)
        if "fills" in visual:
            styles["fills"] = visual["fills"]

    return styles


# ═══════════════════════════════════════════════════════════════
# Extraction principale
# ═══════════════════════════════════════════════════════════════

def extract_sections() -> dict:
    print("\n[sections_extractor] Chargement des fichiers...")

    with open(TREE_OUTPUT_FILE, "r", encoding="utf-8") as f:
        tree = json.load(f)

    architecture_index = _load_architecture_index()
    raw_index = _build_raw_index(MINIMAL_OUTPUT_FILE)
    interactions_index = _build_interactions_index(raw_index)

    result_pages = []
    total_sections = 0
    total_instances = 0

    for canvas in tree.get("document", {}).get("children", []):
        for page in canvas.get("children", []):
            page_id = page.get("id")
            page_name = page.get("name")

            print(f"\n[sections_extractor] Page : '{page_name}' (id={page_id})")

            page_raw = raw_index.get(page_id, {})
            page_styles = _extract_page_styles(page_raw) if page_raw else {}
            page_layout_mode = page_raw.get("layoutMode") if page_raw else None

            raw_children = page.get("children", [])
            sorted_children = _sort_children_by_visual_position(
                raw_children,
                raw_index,
                page_layout_mode,
            )

            print(f"  [TRI] Ordre visuel ({len(sorted_children)} enfants) :")
            for i, child in enumerate(sorted_children):
                raw_child = raw_index.get(child.get("id"))
                if raw_child:
                    y, x = _get_node_position(raw_child)
                    print(f"    {i}: {child.get('name')} (y={y:.0f}, x={x:.0f})")
                else:
                    print(f"    {i}: {child.get('name')} (hors index)")

            ordered_children = []

            for idx, child in enumerate(sorted_children):
                child_id = child.get("id")
                child_name = child.get("name")
                child_type = child.get("type")
                component_id = child.get("componentId")

                # ─── Cas 1 : enfant direct = INSTANCE réutilisable ───
                if child_type == "INSTANCE" and component_id in architecture_index:
                    raw_node = raw_index.get(child_id)

                    if not raw_node:
                        print(
                            f"  [ERREUR] Instance {child_name} "
                            f"(id={child_id}) absente du raw index"
                        )
                        continue

                    arch_entry = architecture_index[component_id]
                    react_name = arch_entry.get("name", child_name)

                    overrides = _collect_all_overrides(raw_node)
                    props_values = _match_overrides_to_props(
                        overrides,
                        arch_entry,
                        react_name,
                    )

                    interaction = interactions_index.get(child_id)
                    # ✅ NOUVEAU : collecter les interactions des enfants
                    child_interactions = _collect_descendant_interactions(raw_node, interactions_index)

                    instance_data = {
                        "id": child_id,
                        "name": child_name,
                        "component_id": component_id,
                        "react_component_name": react_name,
                        "props_values": props_values,
                    }

                    if interaction:
                        instance_data["interaction"] = interaction
                    # ✅ NOUVEAU
                    if child_interactions:
                         instance_data["child_interactions"] = child_interactions    

                    ordered_children.append({
                        "kind": "instance",
                        "order_index": idx,
                        "data": instance_data,
                    })

                    total_instances += 1

                    if interaction:
                        triggers = [i.get("trigger") for i in interaction]
                        print(
                            f"  [INSTANCE] {child_name} -> <{react_name} "
                            f"{list(props_values.keys())} /> interactions={triggers}"
                        )
                    else:
                        print(
                            f"  [INSTANCE] {child_name} -> <{react_name} "
                            f"{list(props_values.keys())} />"
                        )

                # ─── Cas 2 : section libre / frame / groupe ───
                else:
                    raw_node = raw_index.get(child_id)

                    if not raw_node:
                        print(
                            f"  [ERREUR] {child_name} "
                            f"(id={child_id}) absent du raw index"
                        )
                        continue

                    nested_instances: list[dict] = []

                    cleaned = _clean_node_recursive(
                        raw_node,
                        architecture_index,
                        raw_index,
                        interactions_index,
                        nested_instances,
                        depth=0,
                    )

                    cleaned = _inject_absolute_positions(cleaned)
                    cleaned = _flatten_useless_wrappers(cleaned)

                    if cleaned is None:
                        cleaned = {
                            "id": child_id,
                            "type": "FRAME",
                            "name": child_name,
                        }

                    ordered_children.append({
                        "kind": "section",
                        "order_index": idx,
                        "data": cleaned,
                        "nested_instances": nested_instances,
                    })

                    total_sections += 1
                    total_instances += len(nested_instances)

                    if nested_instances:
                        names = [
                            i["react_component_name"]
                            for i in nested_instances
                        ]
                        print(
                            f"  [FRAME]    {child_name} -> section avec "
                            f"{len(nested_instances)} composants : {names}"
                        )
                    else:
                        print(
                            f"  [FRAME]    {child_name} -> section pure "
                            f"(sans instance)"
                        )

            result_pages.append({
                "page_id": page_id,
                "page_name": page_name,
                "page_styles": page_styles,
                "ordered_children": ordered_children,
            })

    result = {
        "total_pages": len(result_pages),
        "total_sections": total_sections,
        "total_instances_referenced": total_instances,
        "pages": result_pages,
    }

    SECTIONS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(SECTIONS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = SECTIONS_OUTPUT_FILE.stat().st_size / 1024

    print(f"\n[sections_extractor] Résumé :")
    print(f"  - Pages                : {len(result_pages)}")
    print(f"  - Sections (libres)    : {total_sections}")
    print(f"  - Instances total      : {total_instances}")
    print(
        f"[sections_extractor] Sauvegardé -> "
        f"{SECTIONS_OUTPUT_FILE} ({size_kb:.1f} KB)"
    )

    return result