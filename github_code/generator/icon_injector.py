"""
icon_injector.py
================
Post-traitement : remplace les SVG bidons générés par le LLM
par les vrais SVG téléchargés depuis Figma.

Pour chaque composant dans components/ dont le nom commence par "Icon" :
  - Trouve son component_id depuis components_reu.json
  - Récupère le vrai SVG depuis icons.json
  - Remplace le <svg>...</svg> dans le .tsx par le vrai
"""

import json
import re
from pathlib import Path
from config.settings import (
    COMPONENT_REU_OUTPUT_FILE,
    ICONS_OUTPUT_FILE,
    COMPONENTS_DIR,
)


def _sanitize_component_name(raw_name: str) -> str:
    """Convertit 'Icon / Linkedin' → 'IconLinkedin'."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", raw_name).strip().split()
    return "".join(p[0].upper() + p[1:] if p else "" for p in cleaned) or "Component"


def _build_name_to_id_map() -> dict[str, str]:
    """Construit le mapping {nom_react: component_id} depuis components_reu.json."""
    with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # ✅ Lire depuis standalone + variant_sets
    all_components = data.get("standalone", []) + data.get("variant_sets", [])
    
    mapping = {}
    for comp in all_components:
        cid = comp.get("component_id")
        name = comp.get("name", "")
        if cid and name:
            react_name = _sanitize_component_name(name)
            mapping[react_name] = cid
    
    return mapping


def _clean_svg_content(svg: str) -> str:
    """Nettoie le SVG pour l'injection JSX :
    - Retire la déclaration XML
    - Convertit les attributs HTML → JSX (kebab-case → camelCase)
    """
    # Retirer <?xml ... ?>
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
    
    # Convertir les attributs kebab-case → camelCase pour JSX
    def kebab_to_camel(match):
        attr = match.group(1)
        parts = attr.split("-")
        return parts[0] + "".join(p.capitalize() for p in parts[1:]) + "="
    
    svg = re.sub(r"([a-z]+(?:-[a-z]+)+)=", kebab_to_camel, svg)
    
    return svg


def _inject_svg_in_file(file_path: Path, real_svg: str) -> bool:
    """Remplace le <svg>...</svg> bidon par le vrai SVG dans un fichier .tsx.
    
    Retourne True si le remplacement a réussi.
    """
    content = file_path.read_text(encoding="utf-8")
    
    # Trouver le bloc <svg>...</svg> (peut contenir des sauts de ligne)
    svg_pattern = re.compile(r"<svg[^>]*>.*?</svg>", re.DOTALL)
    
    if not svg_pattern.search(content):
        print(f"  [WARN] Aucun <svg> trouvé dans {file_path.name}")
        return False
    
    # Nettoyer le vrai SVG pour JSX
    cleaned_svg = _clean_svg_content(real_svg)
    
    # Remplacer (uniquement le premier <svg> trouvé)
    new_content = svg_pattern.sub(cleaned_svg, content, count=1)
    
    file_path.write_text(new_content, encoding="utf-8")
    return True


def run_icon_injector() -> None:
    """Remplace les SVG bidons par les vrais dans tous les composants Icon*."""
    print("\n[icon_injector] === Injection des vrais SVG ===")
    
    # Charger icons.json
    if not ICONS_OUTPUT_FILE.exists():
        print(f"[icon_injector] ERREUR : {ICONS_OUTPUT_FILE} introuvable")
        print("  → Lance d'abord icon_downloader.py")
        return
    
    with open(ICONS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        icons_svg = json.load(f)
    
    print(f"[icon_injector] {len(icons_svg)} icônes disponibles dans icons.json")
    
    # Mapping nom_react → component_id
    name_to_id = _build_name_to_id_map()
    
    # Parcourir les composants générés
    injected = 0
    skipped = 0
    
    for tsx_file in COMPONENTS_DIR.glob("*.tsx"):
        react_name = tsx_file.stem  # ex: "IconLinkedin"
        
        cid = name_to_id.get(react_name)
        if not cid:
            continue
        
        icon_data = icons_svg.get(cid)
        if not icon_data:
            print(f"  [WARN] Pas de SVG pour {react_name} ({cid})")
            skipped += 1
            continue
        
        success = _inject_svg_in_file(tsx_file, icon_data["svg"])
        if success:
            print(f"  ✅ {react_name} injecté ({icon_data['name']})")
            injected += 1
        else:
            skipped += 1
    
    print(f"\n[icon_injector] {injected} injectés, {skipped} skippés")


if __name__ == "__main__":
    run_icon_injector()