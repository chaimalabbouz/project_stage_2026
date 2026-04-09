"""
services/figma/style_converter.py
----------------------------------
Noeud de conversion déterministe Figma -> Tailwind CSS.
Lit : data/processed/figma_cleaned.json & data/component-reu/reusable_components.json
Écrit : data/code_style/processed.json & data/code_style/component_reu.json

CORRECTIONS :
  - Bug 1 : font-family et font-weight → classes Tailwind séparées
  - Bug 2 : dimensions fixes émises même sans HUG/FILL
  - Bug 3 : opacity globale séparée de l'opacity des fills
  - Bug 4 : syntaxe box-shadow Tailwind corrigée (underscores)
  - Bug 5 : cornerRadius individuel pris en compte
  - Bug 6 : strokeWeight retiré de keys_to_delete
"""

import json
from pathlib import Path

IN_PROCESSED = Path("data/processed/figma_cleaned.json")
IN_COMP_REU  = Path("data/component-reu/reusable_components.json")
OUT_DIR      = Path("data/code_style")


class FigmaToTailwindConverter:

    # ------------------------------------------------------------------
    # UTILITAIRES
    # ------------------------------------------------------------------
    @staticmethod
    def _rgba(color: dict) -> str:
        if not color or color.get("a", 1) == 0:
            return ""
        r = round(color["r"] * 255)
        g = round(color["g"] * 255)
        b = round(color["b"] * 255)
        a = round(color.get("a", 1.0), 2)
        if a < 1:
            return f"rgba({r},{g},{b},{a})"
        return f"#{r:02x}{g:02x}{b:02x}"

    # ------------------------------------------------------------------
    # CONVERTISSEURS
    # ------------------------------------------------------------------

    def _convert_fills(self, node: dict) -> str:
        classes = []
        for fill in node.get("fills", []):
            if fill.get("type") == "SOLID" and fill.get("visible", True) is not False:
                color = self._rgba(fill.get("color"))
                if color:
                    classes.append(f"bg-[{color}]")
                    # BUG 3 FIX : bg-opacity séparée de l'opacity globale du nœud
                    fill_opacity = fill.get("opacity", 1.0)
                    node_opacity = node.get("opacity", 1.0)
                    if fill_opacity < 1.0 and abs(fill_opacity - node_opacity) > 0.01:
                        classes.append(f"bg-opacity-[{round(fill_opacity, 2)}]")

        if not classes and node.get("backgroundColor"):
            bg_color = self._rgba(node["backgroundColor"])
            if bg_color:
                classes.append(f"bg-[{bg_color}]")

        return " ".join(classes)

    def _convert_strokes(self, node: dict) -> str:
        classes = []
        strokes = node.get("strokes", [])
        if strokes and strokes[0].get("type") == "SOLID":
            # BUG 6 FIX : lu ici avant d'être supprimé dans keys_to_delete
            weight = node.get("strokeWeight", 1)
            color  = self._rgba(strokes[0].get("color"))
            if color:
                classes.append(f"border-[{round(weight)}px]")
                classes.append(f"border-[{color}]")
        return " ".join(classes)

    def _convert_layout(self, node: dict) -> str:
        classes = []
        layout = node.get("layoutMode")

        if not layout:
            bbox = node.get("absoluteBoundingBox", {})
            w = node.get("width") or bbox.get("width")
            h = node.get("height") or bbox.get("height")
            if w: classes.append(f"w-[{round(w)}px]")
            if h: classes.append(f"h-[{round(h)}px]")
            return " ".join(classes)

        classes.append("flex")
        classes.append("flex-row" if layout == "HORIZONTAL" else "flex-col")

        # BUG 2 FIX : si pas HUG ni FILL → émettre la taille absolue
        h_sizing = node.get("layoutSizingHorizontal")
        if h_sizing == "FILL":
            classes.append("w-full")
        elif h_sizing == "HUG":
            classes.append("w-fit")
        else:
            bbox = node.get("absoluteBoundingBox", {})
            w = node.get("width") or bbox.get("width")
            if w: classes.append(f"w-[{round(w)}px]")

        v_sizing = node.get("layoutSizingVertical")
        if v_sizing == "FILL":
            classes.append("h-full")
        elif v_sizing == "HUG":
            classes.append("h-fit")
        else:
            bbox = node.get("absoluteBoundingBox", {})
            h = node.get("height") or bbox.get("height")
            if h: classes.append(f"h-[{round(h)}px]")

        if node.get("layoutGrow", 0) > 0:
            classes.append("flex-1")

        primary_map = {
            "MIN": "justify-start", "CENTER": "justify-center",
            "MAX": "justify-end",   "SPACE_BETWEEN": "justify-between",
        }
        counter_map = {
            "MIN": "items-start", "CENTER": "items-center",
            "MAX": "items-end",   "BASELINE": "items-baseline",
        }
        p = node.get("primaryAxisAlignItems")
        c = node.get("counterAxisAlignItems")
        if p and primary_map.get(p): classes.append(primary_map[p])
        if c and counter_map.get(c): classes.append(counter_map[c])

        gap = node.get("itemSpacing", 0)
        if gap > 0: classes.append(f"gap-[{round(gap)}px]")

        pt = node.get("paddingTop", 0)
        pb = node.get("paddingBottom", 0)
        pl = node.get("paddingLeft", 0)
        pr = node.get("paddingRight", 0)
        if pt == pb == pl == pr and pt > 0:
            classes.append(f"p-[{round(pt)}px]")
        else:
            if pt > 0: classes.append(f"pt-[{round(pt)}px]")
            if pb > 0: classes.append(f"pb-[{round(pb)}px]")
            if pl > 0: classes.append(f"pl-[{round(pl)}px]")
            if pr > 0: classes.append(f"pr-[{round(pr)}px]")

        if node.get("clipsContent") is True:
            classes.append("overflow-hidden")

        return " ".join(classes)

    FONT_WEIGHT_MAP = {
        100: "thin", 200: "extralight", 300: "light",   400: "normal",
        500: "medium", 600: "semibold", 700: "bold",    800: "extrabold",
        900: "black",
    }

    def _convert_typography(self, node: dict) -> str:
        """
        BUG 1 FIX :
        - Famille  → font-['Inter'] (valeur arbitraire avec quotes)
        - Poids    → font-normal / font-bold / etc. (classe sémantique, pas font-[400])
        Ces deux classes ne collisionnent plus.
        """
        s = node.get("style", {})
        if not s:
            return ""

        classes = []

        # Famille — quotes obligatoires pour les noms avec espaces
        family = s.get("fontFamily", "Inter")
        safe_family = family.replace(" ", "_")
        classes.append(f"font-['{safe_family}']")

        # Taille
        classes.append(f"text-[{s.get('fontSize', 16)}px]")

        # Poids — classe sémantique Tailwind
        weight     = s.get("fontWeight", 400)
        weight_cls = self.FONT_WEIGHT_MAP.get(weight)
        if weight_cls:
            classes.append(f"font-{weight_cls}")
        else:
            classes.append(f"[font-weight:{weight}]")

        # Hauteur de ligne
        line_h = s.get("lineHeightPx")
        if line_h:
            classes.append(f"leading-[{round(line_h, 2)}px]")

        # Letter-spacing
        ls = s.get("letterSpacing", 0)
        if ls != 0:
            classes.append(f"tracking-[{round(ls, 2)}px]")

        # Alignement
        align_map = {
            "CENTER": "text-center",
            "RIGHT":  "text-right",
            "JUSTIFIED": "text-justify",
        }
        align = s.get("textAlignHorizontal")
        if align in align_map:
            classes.append(align_map[align])

        # Couleur texte
        for fill in node.get("fills", []):
            if fill.get("type") == "SOLID" and fill.get("visible", True) is not False:
                color = self._rgba(fill.get("color"))
                if color:
                    classes.append(f"text-[{color}]")
                    fill_opacity = fill.get("opacity", 1.0)
                    if fill_opacity < 1.0:
                        classes.append(f"opacity-[{round(fill_opacity, 2)}]")
                break

        return " ".join(classes)

    def _convert_effects(self, node: dict) -> str:
        """BUG 4 FIX : underscores = espaces dans valeurs arbitraires Tailwind."""
        classes = []
        for eff in node.get("effects", []):
            if eff.get("type") == "DROP_SHADOW" and eff.get("visible", True) is not False:
                x      = eff.get("offset", {}).get("x", 0)
                y      = eff.get("offset", {}).get("y", 4)
                r      = eff.get("radius", 10)
                spread = eff.get("spread", 0)
                color  = self._rgba(eff.get("color")) or "rgba(0,0,0,0.15)"
                classes.append(f"shadow-[{x}px_{y}px_{r}px_{spread}px_{color}]")
        return " ".join(classes)

    def _convert_geometry(self, node: dict) -> str:
        """
        BUG 3 FIX : opacity globale uniquement ici.
        BUG 5 FIX : cornerRadius individuel supporté.
        """
        classes = []

        radius = node.get("cornerRadius")
        if radius and radius > 0:
            classes.append(f"rounded-[{round(radius)}px]")
        else:
            tl = node.get("topLeftRadius", 0)
            tr = node.get("topRightRadius", 0)
            br = node.get("bottomRightRadius", 0)
            bl = node.get("bottomLeftRadius", 0)
            if any([tl, tr, br, bl]):
                classes.append(
                    f"[border-radius:{round(tl)}px_{round(tr)}px_{round(br)}px_{round(bl)}px]"
                )

        opacity = node.get("opacity", 1.0)
        if opacity < 1.0:
            classes.append(f"opacity-[{round(opacity, 2)}]")

        return " ".join(classes)

    # ------------------------------------------------------------------
    # ORCHESTRATEUR DE NŒUD
    # ------------------------------------------------------------------
    def transform_node(self, node):
        if not isinstance(node, dict):
            return node

        tw_classes = []
        node_type  = node.get("type", "")

        if node_type == "TEXT":
            tw_classes.append(self._convert_typography(node))
        else:
            tw_classes.append(self._convert_layout(node))
            tw_classes.append(self._convert_fills(node))
            tw_classes.append(self._convert_strokes(node))

        tw_classes.append(self._convert_effects(node))
        tw_classes.append(self._convert_geometry(node))

        node["tailwind_classes"] = " ".join(cls for cls in tw_classes if cls).strip()

        # BUG 6 FIX : strokeWeight retiré de la liste (déjà consommé dans _convert_strokes)
        keys_to_delete = [
            "style", "fills", "strokes", "effects",
            "layoutMode", "primaryAxisAlignItems", "counterAxisAlignItems",
            "itemSpacing", "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
            "absoluteBoundingBox", "constraints", "cornerRadius",
            "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius",
            "opacity",
            "primaryAxisSizingMode", "counterAxisSizingMode",
            "layoutAlign", "layoutWrap", "cornerSmoothing",
            "backgroundColor", "background",
            "blendMode", "strokeAlign",
            # strokeWeight retiré intentionnellement — déjà lu dans _convert_strokes
            "fontPostScriptName", "lineHeightPercent", "lineHeightPercentFontSize",
            "lineHeightUnit", "textAlignVertical",
            "layoutSizingHorizontal", "layoutSizingVertical", "layoutGrow",
        ]

        for key in keys_to_delete:
            node.pop(key, None)

        if "children" in node:
            node["children"] = [self.transform_node(child) for child in node["children"]]

        return node


# ======================================================================
# FONCTION NŒUD LANGGRAPH
# ======================================================================
def style_converter_node(state: dict) -> dict:
    print("\n[Style Converter] Conversion Figma -> Tailwind en cours...")
    converter = FigmaToTailwindConverter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if IN_PROCESSED.exists():
        with open(IN_PROCESSED, "r", encoding="utf-8") as f:
            processed_data = json.load(f)

        if "document" in processed_data:
            processed_data["document"] = converter.transform_node(processed_data["document"])
        else:
            processed_data = converter.transform_node(processed_data)

        with open(OUT_DIR / "processed.json", "w", encoding="utf-8") as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)
        print("[Style Converter] ✅ processed.json converti avec succès !")

    if IN_COMP_REU.exists():
        with open(IN_COMP_REU, "r", encoding="utf-8") as f:
            comp_reu_data = json.load(f)

        if "components" in comp_reu_data:
            for comp_obj in comp_reu_data["components"]:
                if "definition" in comp_obj and isinstance(comp_obj["definition"], dict):
                    comp_obj["definition"] = converter.transform_node(comp_obj["definition"])

        with open(OUT_DIR / "component_reu.json", "w", encoding="utf-8") as f:
            json.dump(comp_reu_data, f, ensure_ascii=False, indent=2)
        print("[Style Converter] ✅ component_reu.json converti avec succès !")

    print(f"[Style Converter] Terminé ! Fichiers dans {OUT_DIR}\n")

    logs = list(state.get("logs", []))
    logs.append("[Style Converter] JSON nettoyés et prêts pour le Coder Agent.")
    return {"logs": logs}