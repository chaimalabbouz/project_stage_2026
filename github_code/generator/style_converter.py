"""
style_converter.py
==================
Convertisseur DÉTERMINISTE de styles Figma → classes Tailwind.

Reçoit un squelette JSX (avec className="" et data-fname="...")
+ le dict de styles (root + nodes) et remplit chaque className
avec les classes Tailwind correspondantes.

Utilisé entre le LLM #1 (structure) et le LLM #2 (vérification)
dans le pipeline du générateur.
"""

import re
import math
DESKTOP_WIDTH_THRESHOLD = 1200
LARGE_PADDING_THRESHOLD = 120


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _fmt(value) -> str:
    """Formate un nombre : enlève .0 si entier."""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _rgba_str(color: dict) -> str:
    """Convertit {hex, rgb, alpha} en rgba(...) pour les shadows."""
    rgb = color.get("rgb", {})
    r = rgb.get("r", 0)
    g = rgb.get("g", 0)
    b = rgb.get("b", 0)
    a = color.get("alpha", 1.0)
    # Arrondir alpha à 2 décimales
    a = round(a, 2)
    return f"rgba({r},{g},{b},{a})"


# ═══════════════════════════════════════════════════════════════
# CONVERSION PAR CATÉGORIE
# ═══════════════════════════════════════════════════════════════

def _convert_layout(layout: dict) -> list[str]:
    """layoutMode, align, wrap, gap → classes flex ou grid."""
    classes = []

    mode = layout.get("layoutMode")

    # 🔥 AJOUT GRID
    if mode == "GRID":
        classes.append("grid")

        cols = layout.get("gridColumns")
        if cols and cols > 0:
            classes.append(f"grid-cols-{cols}")

    # FLEX existant
    elif mode == "VERTICAL":
        classes.append("flex flex-col")

    elif mode == "HORIZONTAL":
        classes.append("flex flex-row")

    # Axe principal (OK pour flex, ignoré pour grid)
    primary = layout.get("primaryAxisAlignItems")
    if primary == "CENTER":
        classes.append("justify-center")
    elif primary == "SPACE_BETWEEN":
        classes.append("justify-between")
    elif primary == "MAX":
        classes.append("justify-end")
    elif primary == "MIN":
        classes.append("justify-start")

    # Axe secondaire
    counter = layout.get("counterAxisAlignItems")
    if counter == "CENTER":
        classes.append("items-center")
    elif counter == "MIN":
        classes.append("items-start")
    elif counter == "MAX":
        classes.append("items-end")

    # Wrap (uniquement flex)
    if mode != "GRID" and layout.get("layoutWrap") == "WRAP":
        classes.append("flex-wrap")

    # Gap (fonctionne pour flex ET grid ✔️)
    spacing = layout.get("itemSpacing")
    if spacing is not None and spacing > 0:
        classes.append(f"gap-[{_fmt(spacing)}px]")

    return classes

def _convert_sizing(styles: dict) -> list[str]:
    """layoutSizing + width/height → w-/h- classes."""
    classes = []
    layout = styles.get("layout", {})

    # Horizontal
    sh = layout.get("layoutSizingHorizontal")
    if sh == "FILL":
        classes.append("w-full")
    elif sh == "HUG":
        classes.append("w-fit")
    elif sh == "FIXED" and "width" in styles:
        classes.append(f"w-[{_fmt(styles['width'])}px]")
    elif sh is None and "width" in styles:
        classes.append(f"w-[{_fmt(styles['width'])}px]")

    # Vertical
    sv = layout.get("layoutSizingVertical")
    if sv == "FILL":
        classes.append("h-full")
    elif sv == "HUG":
        classes.append("h-fit")
    elif sv == "FIXED" and "height" in styles:
        classes.append(f"h-[{_fmt(styles['height'])}px]")
    elif sv is None and "height" in styles:
        classes.append(f"h-[{_fmt(styles['height'])}px]")

    # Flex grow
    grow = layout.get("layoutGrow")
    if grow is not None and grow >= 1:
        classes.append("flex-1")

    return classes


def _convert_padding(layout: dict) -> list[str]:
    """padding → p-/px-/py-/pl-/pr-/pt-/pb-."""
    classes = []
    padding = layout.get("padding", {})
    if not padding:
        return classes

    pl = padding.get("paddingLeft", 0)
    pr = padding.get("paddingRight", 0)
    pt = padding.get("paddingTop", 0)
    pb = padding.get("paddingBottom", 0)

    if pl == 0 and pr == 0 and pt == 0 and pb == 0:
        return classes

    if pl == pr == pt == pb:
        classes.append(f"p-[{_fmt(pl)}px]")
    elif pl == pr and pt == pb:
        if pl > 0:
            classes.append(f"px-[{_fmt(pl)}px]")
        if pt > 0:
            classes.append(f"py-[{_fmt(pt)}px]")
    else:
        if pl > 0:
            classes.append(f"pl-[{_fmt(pl)}px]")
        if pr > 0:
            classes.append(f"pr-[{_fmt(pr)}px]")
        if pt > 0:
            classes.append(f"pt-[{_fmt(pt)}px]")
        if pb > 0:
            classes.append(f"pb-[{_fmt(pb)}px]")

    return classes


def _convert_fills(fills: list, has_fixed_size: bool = False) -> list[str]:
    """fills → bg-[#hex] ou object-cover."""
    classes = []
    if not isinstance(fills, list):
        return classes

    for fill in fills:
        if not isinstance(fill, dict):
            continue

        # Ignorer les fills invisibles
        if fill.get("visible") is False:
            continue

        ftype = fill.get("type")

        if ftype == "SOLID":
            color = fill.get("color", {})
            hex_val = color.get("hex")
            if hex_val:
                alpha = color.get("alpha", 1.0)
                if alpha < 1.0:
                    # Utiliser rgba pour les fonds semi-transparents
                    rgb = color.get("rgb", {})
                    classes.append(f"bg-[rgba({rgb.get('r', 0)},{rgb.get('g', 0)},{rgb.get('b', 0)},{round(alpha, 2)})]")
                else:
                    classes.append(f"bg-[{hex_val}]")
            break  # Premier fill visible seulement

        elif ftype == "IMAGE":
            scale = fill.get("scaleMode", "FILL")
            if scale == "FILL":
                classes.append("object-cover")
            if scale == "FIT":
                classes.append("object-contain")
            # w-full h-full seulement si pas de dimensions fixes
            if not has_fixed_size:
                classes.append("w-full")
                classes.append("h-full")
            break

    return classes


def _convert_corner_radius(styles: dict) -> list[str]:
    """cornerRadius → rounded-[Npx]."""
    classes = []

    radii = styles.get("rectangleCornerRadii")
    if radii and isinstance(radii, list) and len(radii) == 4:
        tl, tr, br, bl = radii
        if tl == tr == br == bl:
            if tl > 0:
                classes.append(f"rounded-[{_fmt(tl)}px]")
        else:
            if tl > 0:
                classes.append(f"rounded-tl-[{_fmt(tl)}px]")
            if tr > 0:
                classes.append(f"rounded-tr-[{_fmt(tr)}px]")
            if br > 0:
                classes.append(f"rounded-br-[{_fmt(br)}px]")
            if bl > 0:
                classes.append(f"rounded-bl-[{_fmt(bl)}px]")
    elif "cornerRadius" in styles:
        r = styles["cornerRadius"]
        if r and r > 0:
            classes.append(f"rounded-[{_fmt(r)}px]")

    return classes


def _convert_borders(styles: dict) -> list[str]:
    """strokes + strokeWeight → border classes."""
    classes = []

    # Trouver la couleur du stroke (si strokes visibles existent)
    hex_val = ""
    strokes = styles.get("strokes", [])
    if isinstance(strokes, list):
        for stroke in strokes:
            if isinstance(stroke, dict) and stroke.get("visible") is not False:
                if stroke.get("type") == "SOLID" and "color" in stroke:
                    hex_val = stroke["color"].get("hex", "")
                    break

    # Stroke individuel (bottom, top, etc.) — même sans strokes visibles
    individual = styles.get("individualStrokeWeights")
    if isinstance(individual, dict):
        has_individual = False
        for side, prop in [("top", "border-t"), ("bottom", "border-b"),
                           ("left", "border-l"), ("right", "border-r")]:
            w = individual.get(side, 0)
            if w and w > 0:
                classes.append(f"{prop}-[{_fmt(w)}px]")
                has_individual = True
        if has_individual and hex_val:
            classes.append(f"border-[{hex_val}]")
        return classes

    # Stroke uniforme — seulement si strokes visibles
    if hex_val:
        weight = styles.get("strokeWeight", 0)
        if weight and weight > 0:
            classes.append(f"border-[{_fmt(weight)}px]")
            classes.append(f"border-[{hex_val}]")

    return classes


def _convert_effects(effects: list) -> list[str]:
    """DROP_SHADOW → shadow-[...]."""
    classes = []
    if not isinstance(effects, list) or not effects:
        return classes

    shadows = []
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        if eff.get("type") == "DROP_SHADOW":
            offset = eff.get("offset", {})
            x = _fmt(offset.get("x", 0))
            y = _fmt(offset.get("y", 0))
            radius = _fmt(eff.get("radius", 0))
            color = eff.get("color", {})
            rgba = _rgba_str(color)
            shadows.append(f"{x}px_{y}px_{radius}px_{rgba}")

    if shadows:
        classes.append(f"shadow-[{','.join(shadows)}]")

    return classes


def _convert_opacity(styles: dict) -> list[str]:
    """opacity → opacity-[N]."""
    classes = []
    opacity = styles.get("opacity")
    if opacity is not None and opacity != 1 and opacity != 1.0:
        classes.append(f"opacity-[{round(opacity, 2)}]")
    return classes


def _convert_clipping(styles: dict) -> list[str]:
    """clipsContent → overflow-hidden."""
    classes = []
    if styles.get("clipsContent") is True:
        classes.append("overflow-hidden")
    return classes

def _convert_z_index(styles: dict) -> list[str]:
    classes = []
    z = styles.get("zIndex")
    if z is not None:
        classes.append(f"z-[{z}]")
    return classes

def _convert_positioning(styles: dict) -> list[str]:
    classes = []

    position = styles.get("_position")

    if isinstance(position, dict):
        classes.append("absolute")

        top = position.get("top")
        left = position.get("left")

        if top is not None:
            classes.append(f"top-[{_fmt(top)}px]")
        if left is not None:
            classes.append(f"left-[{_fmt(left)}px]")

    elif styles.get("_positioning") == "absolute":
        classes.append("relative")

    return classes

def _convert_text_style(styles: dict) -> list[str]:
    """Typographie TEXT → font/text/leading classes."""
    classes = []

    # Font family
    family = styles.get("fontFamily")
    if family:
        classes.append(f"font-['{family}']")

    # Font size
    size = styles.get("fontSize")
    if size:
        classes.append(f"text-[{_fmt(size)}px]")

    # Font weight
    weight = styles.get("fontWeight")
    weight_map = {
        100: "font-thin",
        200: "font-extralight",
        300: "font-light",
        400: "font-normal",
        500: "font-medium",
        600: "font-semibold",
        700: "font-bold",
        800: "font-extrabold",
        900: "font-black",
    }
    if weight is not None:
        classes.append(weight_map.get(weight, f"font-[{weight}]"))

    # Text color
    color = styles.get("color", {})
    if isinstance(color, dict) and "hex" in color:
        alpha = color.get("alpha", 1.0)
        if alpha < 1.0:
            rgb = color.get("rgb", {})
            classes.append(f"text-[rgba({rgb.get('r', 0)},{rgb.get('g', 0)},{rgb.get('b', 0)},{round(alpha, 2)})]")
        else:
            classes.append(f"text-[{color['hex']}]")

    # Text align
    align = styles.get("textAlignHorizontal")
    if align == "CENTER":
        classes.append("text-center")
    elif align == "RIGHT":
        classes.append("text-right")
    elif align == "LEFT":
        classes.append("text-left")

    # Line height
    lh = styles.get("lineHeightPx")
    if lh:
        classes.append(f"leading-[{_fmt(lh)}px]")

    # Letter spacing
    ls = styles.get("letterSpacing")
    if ls and ls != 0:
        classes.append(f"tracking-[{_fmt(ls)}px]")

    # Text decoration
    deco = styles.get("textDecoration")
    if deco == "UNDERLINE":
        classes.append("underline")
    elif deco == "STRIKETHROUGH":
        classes.append("line-through")

    # Text transform
    case = styles.get("textCase")
    if case == "UPPER":
        classes.append("uppercase")
    elif case == "LOWER":
        classes.append("lowercase")
    elif case == "TITLE":
        classes.append("capitalize")

    return classes


# ═══════════════════════════════════════════════════════════════
# CONVERSION COMPLÈTE D'UN NŒUD
# ═══════════════════════════════════════════════════════════════
def _flatten_layout_styles(styles: dict) -> dict:
    """Extrait layoutMode du sous-objet 'layout' vers la racine."""
    if not isinstance(styles, dict):
        return styles
    
    layout = styles.get("layout", {})
    if layout:
        for key, value in layout.items():
            if key not in styles:
                styles[key] = value
    return styles


def convert_node_styles(node_styles: dict) -> str:
    """Convertit le dict de styles d'un nœud en string de classes Tailwind."""
    # Extraire layoutMode du sous-objet "layout" vers la racine
    if isinstance(node_styles, dict):
        layout = node_styles.get("layout", {})
        if layout:
            for key, value in layout.items():
                if key not in node_styles:
                    node_styles[key] = value
    
    classes = []
    node_type = node_styles.get("type", "")

    if node_type == "TEXT":
        # Texte : typo + sizing + éventuel layout/padding
        classes.extend(_convert_text_style(node_styles))
        classes.extend(_convert_sizing(node_styles))
        layout = node_styles.get("layout", {})
        if layout:
            classes.extend(_convert_layout(layout))
            classes.extend(_convert_padding(layout))
    else:
        # Frame / Rectangle / Vector / etc.
        layout = node_styles.get("layout", {})
        if layout:
            classes.extend(_convert_layout(layout))
            classes.extend(_convert_padding(layout))

        classes.extend(_convert_sizing(node_styles))
        has_fixed = "width" in node_styles and "height" in node_styles
        classes.extend(_convert_fills(node_styles.get("fills", []), has_fixed_size=has_fixed))

    # Commun à tous les types
    classes.extend(_convert_positioning(node_styles))
    classes.extend(_convert_z_index(node_styles))
    classes.extend(_convert_corner_radius(node_styles))
    classes.extend(_convert_borders(node_styles))
    classes.extend(_convert_effects(node_styles.get("effects", [])))
    classes.extend(_convert_opacity(node_styles))
    classes.extend(_convert_clipping(node_styles))

    return " ".join(classes)


def convert_root_styles(root_styles: dict) -> str:
    """Convertit les styles de la racine en string de classes Tailwind."""
    # Extraire layoutMode du sous-objet "layout" vers la racine
    if isinstance(root_styles, dict):
        layout = root_styles.get("layout", {})
        if layout:
            for key, value in layout.items():
                if key not in root_styles:
                    root_styles[key] = value

    classes = []

    classes.extend(_convert_positioning(root_styles))

    layout = root_styles.get("layout", {})
    if layout:
        classes.extend(_convert_layout(layout))
        classes.extend(_convert_padding(layout))

    classes.extend(_convert_sizing(root_styles))
    has_fixed = "width" in root_styles and "height" in root_styles
    classes.extend(_convert_fills(root_styles.get("fills", []), has_fixed_size=has_fixed))
    classes.extend(_convert_corner_radius(root_styles))
    classes.extend(_convert_borders(root_styles))
    classes.extend(_convert_effects(root_styles.get("effects", [])))
    classes.extend(_convert_opacity(root_styles))
    classes.extend(_convert_clipping(root_styles))

    return " ".join(classes)
# ═══════════════════════════════════════════════════════════════
# APPLICATION AU SQUELETTE JSX
# ═══════════════════════════════════════════════════════════════

def apply_styles_to_skeleton(jsx_skeleton: str, styles: dict) -> str:
    """
    Prend le squelette JSX (className="" avec data-fname="...")
    et remplit chaque className avec les classes Tailwind déterministes.

    Args:
        jsx_skeleton: code JSX avec className="" vides
        styles: dict {"root": {...}, "nodes": {"figma_name": {...}, ...}}

    Returns:
        Code JSX avec className pré-remplis
    """
    root_styles = styles.get("root", {})
    nodes_styles = styles.get("nodes", {})

    # Pré-calculer toutes les classes par data-fname
    classes_map = {}
    classes_map["__root__"] = convert_root_styles(root_styles)

    for figma_name, node_styles in nodes_styles.items():
        classes_map[figma_name] = convert_node_styles(node_styles)

    # Regex pour trouver className="" suivi de data-fname="..."
    # Pattern : className="" ... data-fname="nom"
    # Ou : data-fname="nom" ... className=""
    # On traite les deux ordres possibles

    def _replace_classname(match):
        """Remplace className="" par les classes calculées."""
        full = match.group(0)
        fname_match = re.search(r'data-fname="([^"]*)"', full)
        if not fname_match:
            return full

        fname = fname_match.group(1)
        tw_classes = classes_map.get(fname, "")

        if tw_classes:
            return full.replace('className=""', f'className="{tw_classes}"')
        return full

    # Trouver chaque élément JSX qui a à la fois className="" et data-fname=""
    # On matche l'ouverture complète de la balise : <tag ... >
    result = re.sub(
        r'<[a-zA-Z][a-zA-Z0-9]*\s[^>]*className=""[^>]*data-fname="[^"]*"[^>]*>',
        _replace_classname,
        jsx_skeleton,
    )

    # Gérer aussi l'ordre inverse (data-fname avant className)
    result = re.sub(
        r'<[a-zA-Z][a-zA-Z0-9]*\s[^>]*data-fname="[^"]*"[^>]*className=""[^>]*>',
        _replace_classname,
        result,
    )

    return result


# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION DÉTERMINISTE DU JSX DES SECTIONS
# ═══════════════════════════════════════════════════════════════

def _node_to_tag(node_type: str, has_image: bool = False) -> str:
    """Choisit la balise HTML selon le type Figma."""
    if has_image:
        return "img"
    if node_type == "TEXT":
        return "span"
    # FRAME, GROUP, INSTANCE, RECTANGLE, VECTOR, ELLIPSE → div
    return "div"


def _escape_jsx_text(text: str) -> str:
    """Échappe les caractères spéciaux pour le JSX."""
    text = text.replace("{", "&#123;").replace("}", "&#125;")
    return text


def _has_image_fill(node: dict) -> bool:
    """Vérifie si un nœud a un fill IMAGE dans ses styles."""
    styles = node.get("styles", {})
    fills = styles.get("fills", [])
    if isinstance(fills, list):
        for fill in fills:
            if isinstance(fill, dict) and fill.get("type") == "IMAGE":
                return True
    return False


def _build_jsx_call(node: dict) -> str:
    """Construit l'appel JSX depuis un placeholder."""
    raw_name = node.get("react_component_name", "Component")
    
    # ✅ NOUVEAU : sanitizer pour enlever les espaces
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", raw_name).strip().split()
    react_name = "".join(p[0].upper() + p[1:] if p else "" for p in cleaned) or "Component"
    
    props_values = node.get("props_values", {})
    if not props_values:
        return f"<{react_name} />"
    parts = []
    for k, v in props_values.items():
        if isinstance(v, bool):
            parts.append(f"{k}={{{str(v).lower()}}}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}={{{v}}}")
        else:
            safe = str(v).replace('"', '\\"').replace("\n", " ")
            parts.append(f'{k}="{safe}"')
    return f"<{react_name} {' '.join(parts)} />"

def _get_image_src_from_node(node: dict) -> str:
    styles = node.get("styles", {})
    fills = styles.get("fills", [])

    if isinstance(fills, list):
        for fill in fills:
            if isinstance(fill, dict) and fill.get("type") == "IMAGE":
                return fill.get("imageRef", "/placeholder.jpg")

    return "/placeholder.jpg"


def _html_id_from_figma_id(figma_id: str) -> str:
    return "figma-" + str(figma_id).replace(":", "-").replace(";", "-")


def _wrap_jsx_with_interaction(
    jsx: str,
    interaction,
    route_by_node_id: dict,
) -> str:
    """Enveloppe le JSX selon le nouveau format d'interactions."""
    if not interaction:
        return jsx
    
    if not isinstance(interaction, list):
        return jsx
    
    click_interaction = next(
        (i for i in interaction if i.get("trigger") == "ON_CLICK"),
        None,
    )
    if not click_interaction:
        return jsx
    
    actions = click_interaction.get("actions", [])
    if not actions:
        return jsx
    
    first_action = actions[0]
    action_type = first_action.get("type")
    navigation = first_action.get("navigation")
    dest_id = first_action.get("destinationId")
    
    if navigation == "NAVIGATE" and dest_id:
        route = route_by_node_id.get(dest_id)
        if route:
            return f'<Link to="{route}">{jsx}</Link>'
        return jsx
    
    if navigation == "SCROLL_TO" and dest_id:
        html_id = _html_id_from_figma_id(dest_id)
        return (
            f'<button type="button" onClick={{() => '
            f'document.getElementById("{html_id}")?.scrollIntoView({{ behavior: "smooth" }})'
            f'}}>{jsx}</button>'
        )
    
    if navigation == "OVERLAY" and dest_id:
        return (
            f'<button type="button" onClick={{() => '
            f'setActiveOverlay("{dest_id}")'
            f'}}>{jsx}</button>'
        )
    
    if action_type == "BACK":
        return (
            f'<button type="button" onClick={{() => navigate(-1)}}>{jsx}</button>'
        )
    
    return jsx

def _generate_node_jsx(
    node: dict,
    indent: int = 0,
    route_by_node_id: dict | None = None,
) -> str:
    """Génère le JSX d'un nœud de section récursivement."""
    if not isinstance(node, dict):
        return ""

    route_by_node_id = route_by_node_id or {}
    interaction = node.get("interaction")

    node_type = node.get("type", "")
    prefix = "  " * indent

    # ─── Placeholder composant ───
    if node_type == "__COMPONENT_PLACEHOLDER__":
        jsx_call = node.get("jsx_call") or _build_jsx_call(node)
        styles = node.get("styles", {})
        node_id = node.get("id")   # ✅ NOUVEAU
        id_attr = f' id="{_html_id_from_figma_id(node_id)}"' if node_id else ""

        if styles:
            tw_classes = convert_node_styles(styles)
            if tw_classes:
                jsx = (
                    f'<div{id_attr} className="{tw_classes}">\n'
                    f'  {jsx_call}\n'
                    f'</div>'
                )
                jsx = _wrap_jsx_with_interaction(
                    jsx,
                    interaction,
                    route_by_node_id,
                )
                return f"{prefix}{jsx}"

        # ✅ NOUVEAU : envelopper avec id même sans styles
        if node_id:
            jsx = f'<div{id_attr}>{jsx_call}</div>'
        else:
            jsx = jsx_call

        jsx = _wrap_jsx_with_interaction(
            jsx,
            interaction,
            route_by_node_id,
        )
        return f"{prefix}{jsx}"

    name = node.get("name", "")
    styles = node.get("styles", {})
    characters = node.get("characters", "")
    children = node.get("children", [])
    has_image = _has_image_fill(node)

    if styles:
        styles_with_type = {**styles, "type": node_type}
        tw_classes = convert_node_styles(styles_with_type)
    else:
        tw_classes = ""

    class_attr = f' className="{tw_classes}"' if tw_classes else ""

    # ─── Image ───
    if has_image and not children:
        src = _get_image_src_from_node(node)
        jsx = f'<img src="{src}" alt="{name}"{class_attr} />'
        jsx = _wrap_jsx_with_interaction(
            jsx,
            interaction,
            route_by_node_id,
        )
        return f"{prefix}{jsx}"

    # ─── Texte ───
    if node_type == "TEXT" and characters:
        safe_text = _escape_jsx_text(characters)
        jsx = f"<span{class_attr}>{safe_text}</span>"
        jsx = _wrap_jsx_with_interaction(
            jsx,
            interaction,
            route_by_node_id,
        )
        return f"{prefix}{jsx}"

    tag = "div"

    # Pas d'enfants → div vide
    if not children and not characters:
        jsx = f"<{tag}{class_attr}></{tag}>"
        jsx = _wrap_jsx_with_interaction(
            jsx,
            interaction,
            route_by_node_id,
        )
        return f"{prefix}{jsx}"

    # Avec enfants → récursion
    lines = [f"{prefix}<{tag}{class_attr}>"]

    for child in children:
        if isinstance(child, dict):
            child_jsx = _generate_node_jsx(
                child,
                indent + 1,
                route_by_node_id=route_by_node_id,
            )
            if child_jsx:
                lines.append(child_jsx)

    lines.append(f"{prefix}</{tag}>")

    jsx = "\n".join(lines)
    return _wrap_jsx_with_interaction(
        jsx,
        interaction,
        route_by_node_id,
    )

def generate_section_jsx_deterministic(
    section_data: dict,
    route_by_node_id: dict | None = None,
) -> str:
    """Génère le JSX complet d'une section de page de manière déterministe."""
    route_by_node_id = route_by_node_id or {}
    return _generate_node_jsx(
        section_data,
        indent=0,
        route_by_node_id=route_by_node_id,
    )