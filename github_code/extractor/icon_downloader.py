"""
icon_downloader.py
==================
Télécharge les SVG des icônes Figma via l'API.

Détecte les composants "icônes" dans components_reu.json (nom contient "Icon"),
appelle l'API Figma /v1/images en batch, télécharge les SVG et les sauvegarde
dans icons.json sous forme {component_id: {name, svg}}.
"""

import json
import requests
from pathlib import Path
from config.settings import (
    COMPONENT_REU_OUTPUT_FILE,
    ICONS_OUTPUT_FILE,
    FIGMA_API_KEY,
    FIGMA_FILE_KEY,
)


def _is_icon(component: dict) -> bool:
    """Détecte si un composant est une icône (nom contient 'icon')."""
    name = component.get("name", "").lower()
    return "icon" in name


def _get_image_urls(component_ids: list[str]) -> dict[str, str]:
    """Appelle l'API Figma pour récupérer les URLs des SVG."""
    url = f"https://api.figma.com/v1/images/{FIGMA_FILE_KEY}"
    headers = {"X-Figma-Token": FIGMA_API_KEY}
    
    params = {
        "ids": ",".join(component_ids),
        "format": "svg",
    }
    
    print(f"[icon_downloader] Requête API pour {len(component_ids)} icônes...")
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    data = response.json()
    return data.get("images", {})


def _download_svg(url: str) -> str:
    """Télécharge le contenu SVG depuis une URL."""
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def run_icon_downloader() -> dict:
    """Télécharge tous les SVG des icônes et sauvegarde dans icons.json."""
    print("\n[icon_downloader] Chargement de components_reu.json...")
    
    if not FIGMA_API_KEY or not FIGMA_FILE_KEY:
        raise RuntimeError(
            "FIGMA_API_KEY ou FIGMA_FILE_ID manquant dans .env"
        )
    
    with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # ✅ Lire depuis standalone + variant_sets
    all_components = data.get("standalone", []) + data.get("variant_sets", [])
    
    # Identifier les icônes
    icons = []
    for comp in all_components:
        if _is_icon(comp):
            icons.append({
                "id": comp["component_id"],
                "name": comp["name"],
            })
    
    print(f"[icon_downloader] {len(icons)} icônes détectées :")
    for icon in icons:
        print(f"  - {icon['name']} ({icon['id']})")
    
    if not icons:
        print("[icon_downloader] Aucune icône trouvée.")
        return {}
    
    # Récupérer les URLs depuis Figma
    icon_ids = [icon["id"] for icon in icons]
    urls = _get_image_urls(icon_ids)
    
    # Télécharger les SVG
    icons_svg = {}
    for icon in icons:
        cid = icon["id"]
        url = urls.get(cid)
        if not url:
            print(f"  [WARN] Pas d'URL pour {icon['name']} ({cid})")
            continue
        
        try:
            svg = _download_svg(url)
            icons_svg[cid] = {
                "name": icon["name"],
                "svg": svg,
            }
            print(f"  ✅ {icon['name']} téléchargé ({len(svg)} chars)")
        except Exception as e:
            print(f"  [ERREUR] {icon['name']} : {e}")
    
    # Sauvegarder
    ICONS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ICONS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(icons_svg, f, ensure_ascii=False, indent=2)
    
    print(f"\n[icon_downloader] Sauvegardé → {ICONS_OUTPUT_FILE}")
    print(f"[icon_downloader] {len(icons_svg)} icônes téléchargées")
    
    return icons_svg


if __name__ == "__main__":
    run_icon_downloader()