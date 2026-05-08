

import json
import time
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import (
    GROQ_API_KEY,
    COMPONENT_REU_OUTPUT_FILE,
    ARCHITECTURE_FILE,
    MODEL,
)

LLM_DELAY = 4


# ═══════════════════════════════════════════════════════════════
# PROMPT LLM — sémantique uniquement
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Tu es un expert en architecture de composants React TypeScript.

Tu reçois la description d un composant déjà analysé. Son nom React, son id,
ses props et ses styles sont DÉJÀ DÉTERMINÉS. Tu n as PAS à les produire,
ni à les modifier, ni à les renommer, ni à en inventer de nouveaux.

Ton UNIQUE rôle est de fournir les informations sémantiques suivantes :

{
  "suggested_file": "src/components/NomFourni.tsx",
  "layout": "vertical",
  "has_image": true,
  "has_text": true,
  "external_deps": ["@mui/icons-material"],
  "children_structure": ["Titre en haut", "Image au centre", "Bouton en bas"]
}

Règles STRICTES :
- Retourne UNIQUEMENT un JSON valide, sans markdown, sans texte avant/après.
- suggested_file : "src/components/{NomFourni}.tsx" en reprenant EXACTEMENT le
  nom reçu dans le champ "name" du payload. Ne le renomme JAMAIS.
- layout : une seule valeur parmi "vertical", "horizontal", "grid", "none".
  Déduis-la du layoutMode de la racine si présent (VERTICAL->vertical,
  HORIZONTAL->horizontal, NONE->none), sinon choisis selon la disposition
  décrite dans children_preview.
- has_image : true s il y a au moins un nœud IMAGE dans la structure.
- has_text : true s il y a au moins un nœud TEXT dans la structure.
- external_deps : liste de packages npm nécessaires (ex: ["@mui/material"]).
  Liste vide [] si aucune dép externe évidente. N invente pas de deps au hasard.
- children_structure : courte description ordonnée des éléments visuels,
  une chaîne par élément, max 8 chaînes.
- NE PAS inclure de champs autres que les 6 ci-dessus.
- NE PAS produire "name", "component_id", "props", "variant_component_ids",
  "styles" : ces champs sont ajoutés par le code Python après ta réponse.

═══════════════════════════════════════════════════════════════
EXEMPLE 1 — Composant standalone simple
═══════════════════════════════════════════════════════════════

Payload reçu :
{
  "name": "Badge",
  "kind": "standalone",
  "props": [
    {"name": "label", "figma_name": "label", "type": "string"}
  ],
  "children_preview": [
    {"type": "FRAME", "layoutMode": "HORIZONTAL", "name": "badge-container"},
    {"type": "TEXT", "name": "label"}
  ]
}

Réponse attendue :
{
  "suggested_file": "src/components/Badge.tsx",
  "layout": "horizontal",
  "has_image": false,
  "has_text": true,
  "external_deps": [],
  "children_structure": ["Conteneur horizontal avec texte label centré"]
}

═══════════════════════════════════════════════════════════════
EXEMPLE 2 — Variant set avec image
═══════════════════════════════════════════════════════════════

Payload reçu :
{
  "name": "ProductCard",
  "kind": "variant_set",
  "variants_count": 3,
  "props": [
    {"name": "size", "figma_name": "Size", "type": "\"Small\" | \"Large\""},
    {"name": "title", "figma_name": "title", "type": "string"},
    {"name": "price", "figma_name": "price", "type": "string"},
    {"name": "imageUrl", "figma_name": "product-image", "type": "string"}
  ],
  "children_preview": [
    {"type": "FRAME", "layoutMode": "VERTICAL", "name": "card"},
    {"type": "IMAGE", "name": "product-image"},
    {"type": "TEXT", "name": "title"},
    {"type": "TEXT", "name": "price"}
  ]
}

Réponse attendue :
{
  "suggested_file": "src/components/ProductCard.tsx",
  "layout": "vertical",
  "has_image": true,
  "has_text": true,
  "external_deps": [],
  "children_structure": [
    "Image produit en haut",
    "Titre du produit",
    "Prix affiché en bas"
  ]
}
""".strip()


# ═══════════════════════════════════════════════════════════════
# Sanitizer de noms de props (camelCase)
# ═══════════════════════════════════════════════════════════════

def _sanitize_prop_name(name: str) -> str:
    """Convertit un nom Figma en nom de prop JSX valide (camelCase).
    MÊME fonction utilisée dans section_extractor et generateur."""
    if "#" in name:
        name = name.split("#", 1)[0]

    clean = ""
    capitalize_next = False
    for char in name:
        if char.isalnum():
            if capitalize_next:
                clean += char.upper()
                capitalize_next = False
            else:
                clean += char
        else:
            capitalize_next = True

    if clean and clean[0].isupper():
        clean = clean[0].lower() + clean[1:]

    return clean or "value"


# ═══════════════════════════════════════════════════════════════
# SECTION 1 — EXTRACTION DES PROPS (3 sources + fusion)
# ═══════════════════════════════════════════════════════════════

def _extract_text_props(definition: dict) -> list[dict]:
    """Scanne les nœuds TEXT → une prop string par TEXT unique."""
    props = []
    seen = set()

    def _scan(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "TEXT" and "characters" in node:
            figma_name = node.get("name", "")
            if figma_name and figma_name not in seen:
                seen.add(figma_name)
                props.append({
                    "name": _sanitize_prop_name(figma_name),
                    "figma_name": figma_name,
                    "type": "string",
                    "default": node["characters"],
                    "source": "text",
                })
        for child in node.get("children", []):
            _scan(child)

    _scan(definition)
    return props


def _node_has_image_fill(node: dict) -> tuple[bool, str]:
    """Retourne (has_image, imageRef)."""
    fills = node.get("fills", [])
    if not isinstance(fills, list):
        return False, ""
    for fill in fills:
        if isinstance(fill, dict) and fill.get("type") == "IMAGE":
            return True, fill.get("imageRef", "")
    return False, ""


def _extract_image_props(definition: dict) -> list[dict]:
    """Scanne les nœuds avec fill IMAGE → prop string (URL) + suffixe Url."""
    props = []
    seen = set()

    def _scan(node):
        if not isinstance(node, dict):
            return
        has_img, image_ref = _node_has_image_fill(node)
        if has_img:
            figma_name = node.get("name", "")
            if figma_name and figma_name not in seen:
                seen.add(figma_name)
                base = _sanitize_prop_name(figma_name)
                prop_name = base if base.lower().endswith("url") else f"{base}Url"
                props.append({
                    "name": prop_name,
                    "figma_name": figma_name,
                    "type": "string",
                    "default": image_ref,
                    "source": "image",
                })
        for child in node.get("children", []):
            _scan(child)

    _scan(definition)
    return props


def _extract_figma_declared_props(figma_props: dict) -> list[dict]:
    """Lit componentPropertyDefinitions → props avec types React."""
    if not isinstance(figma_props, dict):
        return []

    props = []
    for figma_name, prop_def in figma_props.items():
        if not isinstance(prop_def, dict):
            continue
        prop_type = prop_def.get("type", "TEXT")
        default = prop_def.get("default")

        if prop_type == "VARIANT":
            options = prop_def.get("options", [])
            react_type = " | ".join(f'"{o}"' for o in options) if options else "string"
        elif prop_type == "BOOLEAN":
            react_type = "boolean"
        elif prop_type == "INSTANCE_SWAP":
            react_type = "ReactNode"
        else:
            react_type = "string"

        props.append({
            "name": _sanitize_prop_name(figma_name),
            "figma_name": figma_name,
            "type": react_type,
            "default": default,
            "source": prop_type.lower(),
        })

    return props


def _merge_props(text_props, image_props, declared_props):
    """Fusionne les 3 sources. Clé = figma_name."""
    merged = {}

    for prop in declared_props:
        merged[prop["figma_name"]] = {**prop, "figma_declared": True}

    for prop in text_props:
        key = prop["figma_name"]
        if key in merged:
            if merged[key].get("source") == "text":
                merged[key] = {**prop, "figma_declared": True}
        else:
            merged[key] = {**prop, "figma_declared": False}

    for prop in image_props:
        key = prop["figma_name"]
        if key not in merged:
            merged[key] = {**prop, "figma_declared": False}

    return list(merged.values())


def _extract_props_union(variants, set_figma_props):
    """Union des props sur toutes les variantes d'un variant_set."""
    if not variants:
        return []

    total = len(variants)
    accumulator = {}

    set_declared = _extract_figma_declared_props(set_figma_props)
    for prop in set_declared:
        accumulator[prop["figma_name"]] = {
            "prop": {**prop, "figma_declared": True, "from_set": True},
            "count": total,
        }

    for variant in variants:
        definition = variant.get("definition", {})
        variant_figma_props = variant.get("definition", {}).get("props", {})
        variant_declared = _extract_figma_declared_props(variant_figma_props)
        variant_text = _extract_text_props(definition)
        variant_image = _extract_image_props(definition)
        local_merged = _merge_props(variant_text, variant_image, variant_declared)

        for prop in local_merged:
            key = prop["figma_name"]
            if key in accumulator:
                accumulator[key]["count"] += 1
            else:
                accumulator[key] = {"prop": prop, "count": 1}

    final_props = []
    for entry in accumulator.values():
        prop = entry["prop"]
        count = entry["count"]
        is_required = prop.get("from_set", False) or (count == total)
        final_props.append({**prop, "required": is_required})

    return final_props


# ═══════════════════════════════════════════════════════════════
# SECTION 2 — EXTRACTION DES STYLES (100% déterministe)
# Objectif : valeurs brutes Figma pour que le LLM style les convertisse
# en Tailwind arbitraire avec ≥80% de fidélité visuelle.
# ═══════════════════════════════════════════════════════════════

def _rgba_to_hex(color, opacity=None):
    """Convertit {r,g,b,a} Figma (0..1) en hex + rgb + alpha."""
    if not isinstance(color, dict):
        return {}
    r = int(round(color.get("r", 0) * 255))
    g = int(round(color.get("g", 0) * 255))
    b = int(round(color.get("b", 0) * 255))
    a = color.get("a", 1.0)
    if opacity is not None:
        a = a * opacity
    return {
        "hex": f"#{r:02x}{g:02x}{b:02x}",
        "rgb": {"r": r, "g": g, "b": b},
        "alpha": round(a, 3),
    }


def _simplify_paint(paint):
    """Simplifie un fill/stroke pour le LLM de style."""
    if not isinstance(paint, dict):
        return {}

    result = {"type": paint.get("type")}
    if paint.get("visible") is False:
        result["visible"] = False
    if "opacity" in paint:
        result["opacity"] = paint["opacity"]

    ptype = paint.get("type", "")
    if ptype == "SOLID" and "color" in paint:
        result["color"] = _rgba_to_hex(paint["color"], paint.get("opacity"))
    elif ptype in ("GRADIENT_LINEAR", "GRADIENT_RADIAL",
                   "GRADIENT_ANGULAR", "GRADIENT_DIAMOND"):
        stops = paint.get("gradientStops", [])
        result["gradientStops"] = [
            {"position": s.get("position"),
             "color": _rgba_to_hex(s.get("color", {}))}
            for s in stops if isinstance(s, dict)
        ]
        if "gradientHandlePositions" in paint:
            result["gradientHandlePositions"] = paint["gradientHandlePositions"]
    elif ptype == "IMAGE":
        result["imageRef"] = paint.get("imageRef", "")
        if "scaleMode" in paint:
            result["scaleMode"] = paint["scaleMode"]

    return result


def _simplify_effects(effects):
    """Nettoie ombres/blur pour le LLM."""
    if not isinstance(effects, list):
        return []
    out = []
    for eff in effects:
        if not isinstance(eff, dict) or eff.get("visible") is False:
            continue
        item = {"type": eff.get("type")}
        for key in ("radius", "spread", "offset", "blendMode"):
            if key in eff:
                item[key] = eff[key]
        if "color" in eff:
            item["color"] = _rgba_to_hex(eff["color"])
        out.append(item)
    return out


def _extract_size(node):
    """width/height depuis absoluteBoundingBox ou size."""
    box = node.get("absoluteBoundingBox") or node.get("size")
    if isinstance(box, dict):
        w, h = box.get("width"), box.get("height")
        out = {}
        if w is not None:
            out["width"] = round(w, 2) if isinstance(w, float) else w
        if h is not None:
            out["height"] = round(h, 2) if isinstance(h, float) else h
        return out
    return {}


def _extract_layout_style(node):
    """Layout flex (layoutMode, padding, gap, align)."""
    layout = {}
    for key in ("layoutMode", "primaryAxisAlignItems", "counterAxisAlignItems",
                "primaryAxisSizingMode", "counterAxisSizingMode",
                "layoutWrap", "layoutAlign", "layoutGrow",
                "layoutSizingHorizontal", "layoutSizingVertical"):
        if key in node:
            layout[key] = node[key]

    padding = {}
    for side in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom"):
        if side in node:
            padding[side] = node[side]
    if padding:
        layout["padding"] = padding

    if "itemSpacing" in node:
        layout["itemSpacing"] = node["itemSpacing"]

    return layout


def _extract_corner_radius(node):
    """Radius uniforme ou asymétrique."""
    out = {}
    if "cornerRadius" in node:
        out["cornerRadius"] = node["cornerRadius"]
    if "rectangleCornerRadii" in node:
        out["rectangleCornerRadii"] = node["rectangleCornerRadii"]
    return out


def _extract_borders(node):
    """Strokes + weight + alignement."""
    out = {}
    if "strokes" in node and isinstance(node["strokes"], list) and node["strokes"]:
        out["strokes"] = [_simplify_paint(s) for s in node["strokes"]]
    for key in ("strokeWeight", "individualStrokeWeights", "strokeAlign", "strokeDashes"):
        if key in node:
            out[key] = node[key]
    return out


def _extract_common_visual(node):
    """fills + radius + borders + effects + opacity (sans layout)."""
    out = {}
    if "fills" in node and isinstance(node["fills"], list) and node["fills"]:
        out["fills"] = [_simplify_paint(f) for f in node["fills"]]
    out.update(_extract_corner_radius(node))
    out.update(_extract_borders(node))

    effects = _simplify_effects(node.get("effects", []))
    if effects:
        out["effects"] = effects

    if "opacity" in node and node["opacity"] != 1:
        out["opacity"] = node["opacity"]

    if "blendMode" in node and node["blendMode"] not in (None, "PASS_THROUGH", "NORMAL"):
        out["blendMode"] = node["blendMode"]

    return out


def _extract_text_style(node):
    """Typographie d'un nœud TEXT + couleur."""
    style = node.get("style", {})
    if not isinstance(style, dict):
        style = {}

    keys = (
        "fontFamily", "fontPostScriptName", "fontWeight", "fontSize",
        "textAlignHorizontal", "textAlignVertical",
        "letterSpacing", "lineHeightPx", "lineHeightPercent",
        "lineHeightPercentFontSize", "lineHeightUnit",
        "textCase", "textDecoration",
        "paragraphSpacing", "paragraphIndent",
    )
    out = {k: style[k] for k in keys if k in style}

    # Couleur = premier fill SOLID visible
    fills = node.get("fills", [])
    if isinstance(fills, list):
        for fill in fills:
            if (isinstance(fill, dict)
                and fill.get("type") == "SOLID"
                and fill.get("visible", True)
                and "color" in fill):
                out["color"] = _rgba_to_hex(fill["color"], fill.get("opacity"))
                break

    return out


def _extract_root_styles(root_node):
    """Styles complets du nœud racine."""
    out = {}
    out.update(_extract_size(root_node))
    layout = _extract_layout_style(root_node)
    if layout:
        out["layout"] = layout
    out.update(_extract_common_visual(root_node))
    return out


def _should_style_node(node):
    """True si le nœud mérite son propre bloc de styles."""
    ntype = node.get("type", "")

    if ntype == "TEXT":
        return True
    if ntype in ("RECTANGLE", "ELLIPSE", "VECTOR", "STAR", "LINE", "POLYGON"):
        return True
    if ntype in ("FRAME", "GROUP", "INSTANCE", "COMPONENT"):
        if "layoutMode" in node and node["layoutMode"] != "NONE":
            return True
        if node.get("fills") or node.get("strokes") or node.get("cornerRadius"):
            return True
        if node.get("effects"):
            return True

    return False


def _extract_node_styles(node):
    """Styles selon le type du nœud."""
    ntype = node.get("type", "")
    out = {"type": ntype}

    if ntype == "TEXT":
        out.update(_extract_text_style(node))
        out.update(_extract_size(node))
        return out

    out.update(_extract_size(node))
    layout = _extract_layout_style(node)
    if layout:
        out["layout"] = layout
    out.update(_extract_common_visual(node))
    return out


def _collect_styled_nodes(definition):
    """Dict indexé par figma_name des nœuds stylés (hors racine)."""
    styled = {}
    seen = set()

    def _scan(node, is_root=False):
        if not isinstance(node, dict):
            return
        if not is_root and _should_style_node(node):
            figma_name = node.get("name", "")
            if figma_name and figma_name not in seen:
                seen.add(figma_name)
                styled[figma_name] = _extract_node_styles(node)
        for child in node.get("children", []):
            _scan(child, is_root=False)

    _scan(definition, is_root=True)
    return styled


def _extract_styles_full(definition):
    """{root: {...}, nodes: {figma_name: {...}}}"""
    return {
        "root": _extract_root_styles(definition),
        "nodes": _collect_styled_nodes(definition),
    }


def _extract_variants_styles(variants):
    """Styles de chaque variante, indexés par component_id de la variante."""
    result = {}
    for variant in variants:
        vid = variant.get("component_id")
        if not vid:
            continue
        definition = variant.get("definition", {})
        # AJOUT : remonter root_style au niveau definition
        root_style = definition.pop("root_style", {})
        definition.update(root_style)
        result[vid] = _extract_styles_full(definition)
    return result




def _extract_imports(definition, catalog):
    """Scanne les INSTANCE dans les children et classe en local/external."""
    local = []
    external = []
    seen = set()

    def _scan(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "INSTANCE":
            comp_id = node.get("componentId")
            if comp_id and comp_id not in seen:
                seen.add(comp_id)
                if comp_id in catalog:
                    local.append({
                        "name": catalog[comp_id]["name"],
                        "component_id": comp_id,
                        "props": catalog[comp_id].get("props", []),
                    })
                else:
                    external.append({
                        "name": node.get("name", "Unknown"),
                        "component_id": comp_id,
                    })
        for child in node.get("children", []):
            _scan(child)

    _scan(definition)
    return {"local": local, "external": external}




def _compute_generation_order(components_architecture):
    """Tri topologique : composants sans dépendances locales d'abord."""
    id_to_index = {}
    for i, comp in enumerate(components_architecture):
        id_to_index[comp["component_id"]] = i
        for vid in comp.get("variant_component_ids", []):
            id_to_index[vid] = i

    visited = set()
    order = []

    def _visit(index):
        if index in visited:
            return
        visited.add(index)
        comp = components_architecture[index]
        for dep in comp.get("imports", {}).get("local", []):
            dep_index = id_to_index.get(dep["component_id"])
            if dep_index is not None and dep_index != index:
                _visit(dep_index)
        order.append(index)

    for i in range(len(components_architecture)):
        _visit(i)

    return [components_architecture[i]["name"] for i in order]



# ═══════════════════════════════════════════════════════════════
# Simplification pour le payload LLM
# ═══════════════════════════════════════════════════════════════

def _simplify_for_llm(node, max_depth=4, depth=0):
    """Définition allégée : pas d'IDs, pas de couleurs, pas de bounds."""
    if not isinstance(node, dict):
        return {}

    simplified = {"type": node.get("type"), "name": node.get("name")}

    if "layoutMode" in node:
        simplified["layoutMode"] = node["layoutMode"]

    has_img, _ = _node_has_image_fill(node)
    if has_img:
        simplified["hasImageFill"] = True

    if node.get("type") == "TEXT" and "characters" in node:
        simplified["textPreview"] = node["characters"][:30]

    if depth < max_depth and "children" in node:
        children = node["children"]
        if isinstance(children, list):
            simplified["children"] = [
                _simplify_for_llm(c, max_depth, depth + 1)
                for c in children[:10]
                if isinstance(c, dict)
            ]

    return {k: v for k, v in simplified.items() if v is not None}


# ═══════════════════════════════════════════════════════════════
# Appel LLM
# ═══════════════════════════════════════════════════════════════

def _call_llm(system_prompt, user_content, llm):
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1]).strip()
            time.sleep(LLM_DELAY)
            return raw
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = (attempt + 1) * 6
                print(f"  [RATE LIMIT] Attente {wait}s ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise e
    raise RuntimeError("Rate limit : max retries atteint")


def _validate_llm_response(data):
    required = ["suggested_file", "layout", "has_image", "has_text",
                "external_deps", "children_structure"]
    for field in required:
        if field not in data:
            return False, f"Champ manquant : {field}"
    if data["layout"] not in ("vertical", "horizontal", "grid", "none"):
        return False, f"layout invalide : {data['layout']}"
    if not isinstance(data["external_deps"], list):
        return False, "external_deps doit être une liste"
    if not isinstance(data["children_structure"], list):
        return False, "children_structure doit être une liste"
    return True, ""


def _fallback_semantic(name, props, simplified):
    """Sémantique par défaut si LLM échoue."""
    has_image = any(p.get("source") == "image" for p in props)
    has_text = any(p.get("source") == "text" for p in props)
    layout_mode = simplified.get("layoutMode", "")
    layout_map = {"VERTICAL": "vertical", "HORIZONTAL": "horizontal"}
    layout = layout_map.get(layout_mode, "none")
    return {
        "suggested_file": f"src/components/{name}.tsx",
        "layout": layout,
        "has_image": has_image,
        "has_text": has_text,
        "external_deps": [],
        "children_structure": [f"{name} — structure générée par fallback"],
    }


# ═══════════════════════════════════════════════════════════════
# Construction d'une entrée complète
# ═══════════════════════════════════════════════════════════════

def _build_architecture_entry(
    *,
    name,
    component_id,
    kind,
    props,
    styles,
    simplified_definition,
    variant_component_ids,
    component_set_id,
    variants_count,
    variants_styles,
    imports,
    llm,
):
    """Assemble une entrée : identity + architecture + styles."""
    llm_payload = {
        "name": name,
        "kind": kind,
        "variants_count": variants_count,
        "props": [
            {"name": p["name"], "figma_name": p["figma_name"], "type": p["type"]}
            for p in props
        ],
        "children_preview": simplified_definition,
    }

    payload_str = json.dumps(llm_payload, ensure_ascii=False, separators=(",", ":"))
    raw_text = _call_llm(SYSTEM_PROMPT,
                         f"Voici le composant à analyser :\n\n{payload_str}",
                         llm)

    llm_data = {}
    try:
        parsed = json.loads(raw_text)
        is_valid, err = _validate_llm_response(parsed)
        if is_valid:
            llm_data = parsed
        else:
            print(f"  [WARN] Réponse LLM invalide pour {name} : {err}")
            llm_data = _fallback_semantic(name, props, simplified_definition)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON invalide pour {name} : {e}")
        print(f"  Réponse brute : {raw_text[:200]}")
        llm_data = _fallback_semantic(name, props, simplified_definition)

    # Forcer le bon chemin
    llm_data["suggested_file"] = f"src/components/{name}.tsx"

    # Si variant_set : injecter les styles par variante DANS styles
    if variants_styles is not None:
        styles = {**styles, "styles_by_variant": variants_styles}

    entry = {
        "component_id": component_id,
        "name": name,
        "kind": kind,
        "suggested_file": llm_data["suggested_file"],
        "variant_component_ids": variant_component_ids,
        "architecture": {
            "props": props,
            "layout": llm_data["layout"],
            "has_image": llm_data["has_image"],
            "has_text": llm_data["has_text"],
            "external_deps": llm_data["external_deps"],
            "children_structure": llm_data["children_structure"],
            "children_tree": simplified_definition,
        },
        "styles": styles,
        "imports": imports,
    }

    if component_set_id:
        entry["component_set_id"] = component_set_id

    return entry


# ═══════════════════════════════════════════════════════════════
# Point d'entrée
# ═══════════════════════════════════════════════════════════════

def run_architecte():
    print("\n[architecte] Chargement des fichiers...")

    with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
        reu_data = json.load(f)

        # AJOUT : construire le catalogue {componentId: {name, props}}
        catalog = {}
        for comp in reu_data.get("standalone", []):
          catalog[comp["component_id"]] = {
            "name": comp["name"],
            "props": comp.get("props", {}),
          }
        for vset in reu_data.get("variant_sets", []):
          for variant in vset.get("variants", []):
            catalog[variant["component_id"]] = {
                "name": vset["name"],
                "props": vset.get("props", {}),
            }

    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY, temperature=0)
    components_architecture = []

    # ─── Standalone ───
    for comp in reu_data.get("standalone", []):
        component_id = comp["component_id"]
        name = comp["name"]
        print(f"[architecte] Standalone : {name}...")

        definition = comp.get("definition", {})
        # AJOUT : remonter root_style au niveau definition
        root_style = definition.pop("root_style", {})
        definition.update(root_style)
        figma_props = comp.get("props", {})

        # Props déterministes
        text_props = _extract_text_props(definition)
        image_props = _extract_image_props(definition)
        declared_props = _extract_figma_declared_props(figma_props)
        final_props = _merge_props(text_props, image_props, declared_props)
        for p in final_props:
            p.setdefault("required", True)

        # Styles déterministes
        styles = _extract_styles_full(definition)
        imports = _extract_imports(definition, catalog)

        # Payload LLM
        simplified = _simplify_for_llm(definition)

        entry = _build_architecture_entry(
            name=name,
            component_id=component_id,
            kind="standalone",
            props=final_props,
            styles=styles,
            simplified_definition=simplified,
            variant_component_ids=[component_id],
            component_set_id=None,
            variants_count=1,
            variants_styles=None,
            imports= imports,
            llm=llm,
        )

        components_architecture.append(entry)
        prop_names = [p["name"] for p in final_props]
        node_count = len(styles["nodes"])
        print(f"[architecte] OK — {name} : {len(final_props)} props, "
              f"{node_count} nœuds stylés. Props={prop_names}")

    # ─── Variant sets ───
    for vset in reu_data.get("variant_sets", []):
        set_id = vset["component_set_id"]
        name = vset["name"]
        variants = vset.get("variants", [])
        set_figma_props = vset.get("props", {})

        print(f"[architecte] Variant set : {name} ({len(variants)} variantes)...")

        final_props = _extract_props_union(variants, set_figma_props)

        first_def = variants[0].get("definition", {}) if variants else {}
        # AJOUT : remonter root_style au niveau definition
        root_style = first_def.pop("root_style", {})
        first_def.update(root_style)
        base_styles = _extract_styles_full(first_def)
        variants_styles = _extract_variants_styles(variants)
        imports = _extract_imports(first_def, catalog)

        simplified = _simplify_for_llm(first_def)
        variant_ids = [v["component_id"] for v in variants]

        entry = _build_architecture_entry(
            name=name,
            component_id=set_id,
            kind="variant_set",
            props=final_props,
            styles=base_styles,
            simplified_definition=simplified,
            variant_component_ids=variant_ids,
            component_set_id=set_id,
            variants_count=len(variants),
            variants_styles=variants_styles,
            imports=imports,
            
            llm=llm,
        )

        components_architecture.append(entry)
        prop_names = [p["name"] for p in final_props]
        node_count = len(base_styles["nodes"])
        print(f"[architecte] OK — {name} : {len(final_props)} props (union), "
              f"{node_count} nœuds stylés. Props={prop_names}")

    # ─── Sauvegarde ───
    generation_order = _compute_generation_order(components_architecture)
    result = {
        "generation_order": generation_order,    # ← AJOUT
        "total_components": len(components_architecture),
        "components": components_architecture,
    }

    ARCHITECTURE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ARCHITECTURE_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[architecte] Architecture terminée — {len(components_architecture)} composants.")
    print(f"[architecte] Sauvegardé -> {ARCHITECTURE_FILE}")

    return result