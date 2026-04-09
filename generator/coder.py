import json
import time
from pathlib import Path
from typing import Any

from config.settings import RAW_OUTPUT_FILE
from llm.client import get_llm, MODELS
from generator.prompts import get_component_prompt, get_section_prompt, get_assembly_prompt


# ---------------------------------------------------------------------------
# Clés Figma conservées pour la génération JSX/Tailwind
# ---------------------------------------------------------------------------
_ALLOWED_KEYS = {
    "id", "name", "type",
    "layoutMode", "layoutAlign",
    "layoutSizingHorizontal", "layoutSizingVertical",
    "primaryAxisAlignItems", "counterAxisAlignItems",
    "itemSpacing",
    "paddingLeft", "paddingRight", "paddingTop", "paddingBottom",
    "fills", "strokes", "strokeWeight", "cornerRadius",
    "characters", "style",
    "componentId", "componentProperties",
    "children",
}

_FILL_KEYS  = {"type", "color", "opacity"}
_STYLE_KEYS = {
    "fontFamily", "fontWeight", "fontSize",
    "textAlignHorizontal", "lineHeightPx",
    "letterSpacing", "textCase",
}

_MAX_DEPTH    = 6   # profondeur max de récursion dans l'arbre Figma
_MAX_CHILDREN = 20  # max enfants par nœud


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        print(f"[Coder] Fichier introuvable : {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[Coder] Erreur JSON ({path}) : {exc}")
        return None


def _write_file(full_path: Path, content: str) -> None:
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Recherche de nœud Figma
# ---------------------------------------------------------------------------

def _find_node_by_id(tree: dict | list, target_id: str) -> dict | None:
    if isinstance(tree, dict):
        if tree.get("id") == target_id:
            return tree
        for child in tree.get("children", []):
            result = _find_node_by_id(child, target_id)
            if result:
                return result
    elif isinstance(tree, list):
        for item in tree:
            result = _find_node_by_id(item, target_id)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------
# Nettoyage du JSON Figma
# ---------------------------------------------------------------------------

def _clean_fills(fills: list) -> list:
    if not isinstance(fills, list):
        return []
    result = []
    for f in fills:
        if not isinstance(f, dict):
            continue
        cleaned = {k: v for k, v in f.items() if k in _FILL_KEYS}
        if "color" in cleaned and isinstance(cleaned["color"], dict):
            cleaned["color"] = {k: round(v, 3) for k, v in cleaned["color"].items()}
        result.append(cleaned)
    return result


def _clean_style(style: dict) -> dict:
    if not isinstance(style, dict):
        return {}
    return {k: v for k, v in style.items() if k in _STYLE_KEYS}


def _clean_node(node: dict | list, depth: int = 0) -> dict | list:
    """Élague récursivement un nœud Figma — ne garde que l'essentiel."""
    if isinstance(node, list):
        return [_clean_node(item, depth) for item in node if isinstance(item, dict)]

    if not isinstance(node, dict):
        return node

    # Trop profond → stub minimal
    if depth > _MAX_DEPTH:
        return {
            "id":   node.get("id"),
            "name": node.get("name"),
            "type": node.get("type"),
        }

    cleaned: dict[str, Any] = {}

    for key, value in node.items():
        if key not in _ALLOWED_KEYS:
            continue

        if key in ("fills", "strokes"):
            cleaned[key] = _clean_fills(value)

        elif key == "style":
            s = _clean_style(value)
            if s:
                cleaned[key] = s

        elif key == "children" and isinstance(value, list):
            children = [c for c in value if isinstance(c, dict)]
            if len(children) > _MAX_CHILDREN:
                children = children[:_MAX_CHILDREN]
            cleaned["children"] = [_clean_node(child, depth + 1) for child in children]

        else:
            cleaned[key] = value

    return cleaned


# ---------------------------------------------------------------------------
# Récupération du contexte Figma nettoyé
# ---------------------------------------------------------------------------

def _get_cleaned_node(node_id: str, raw_tree: dict) -> dict:
    """Trouve un nœud par ID dans le JSON brut et le nettoie."""
    document_children = raw_tree.get("document", {}).get("children", [])
    for canvas in document_children:
        raw_node = _find_node_by_id(canvas, node_id)
        if raw_node:
            return _clean_node(raw_node)
    return {}


# ---------------------------------------------------------------------------
# Nettoyage du code généré
# ---------------------------------------------------------------------------

def _strip_fences(code: str) -> str:
    """Supprime les balises markdown (```jsx, ```, etc.)."""
    for fence in ("```jsx", "```javascript", "```tsx", "```"):
        if fence in code:
            code = code.split(fence, 1)[1]
            break
    if "```" in code:
        code = code.split("```", 1)[0]
    return code.strip()


# ---------------------------------------------------------------------------
# Appel LLM avec retry
# ---------------------------------------------------------------------------

def _call_llm(llm: Any, prompt: Any, max_retries: int = 3, delay: float = 65.0) -> str | None:
    """
    Invoque le LLM via une chaîne LCEL.
    Gère les erreurs Groq :
      - 413 : requête trop lourde → abandon immédiat
      - 429 : rate-limit → attend `delay` secondes et réessaie
    """
    chain = prompt | llm

    for attempt in range(1, max_retries + 1):
        try:
            response = chain.invoke({})
            return response.content

        except Exception as exc:
            err = str(exc)

            if "413" in err:
                print(f"[Coder]   ⚠️  Requête trop lourde (413) — abandon.")
                return None

            if "429" in err or "rate_limit" in err.lower():
                if attempt < max_retries:
                    print(f"[Coder]   ⚠️  Rate-limit Groq (tentative {attempt}/{max_retries}) — attente {delay:.0f}s...")
                    time.sleep(delay)
                    continue
                print("[Coder]   ⚠️  Rate-limit : toutes les tentatives épuisées.")
                return None

            print(f"[Coder]   ❌ Erreur LLM inattendue : {exc}")
            return None

    return None


# ---------------------------------------------------------------------------
# Génération d'un composant réutilisable (type != "page")
# ---------------------------------------------------------------------------

def _generate_component(
    file_info: dict,
    raw_tree: dict,
    existing_components: dict[str, str],
    llm: Any,
) -> str | None:
    """Génère le code d'un composant réutilisable en 1 appel LLM."""
    node_id = file_info.get("figma_node_id", "")
    figma_ctx = _get_cleaned_node(node_id, raw_tree) if node_id else {}

    if not figma_ctx:
        print(f"[Coder]   ATTENTION : nœud '{node_id}' introuvable, contexte vide.")

    prompt = get_component_prompt(
        component_info=file_info,
        figma_json=figma_ctx,
        existing_components=existing_components,
    )
    return _call_llm(llm, prompt)


# ---------------------------------------------------------------------------
# Génération d'une page (type == "page") — section par section
# ---------------------------------------------------------------------------

def _generate_page(
    file_info: dict,
    raw_tree: dict,
    existing_components: dict[str, str],
    llm: Any,
) -> str | None:
    """
    Génère une page React en 3 phases (approche de l'ancien generateur.py) :
      1. Récupère les enfants directs du nœud page = sections
      2. Génère le JSX de chaque section séparément
      3. Assemble le tout en un composant page complet
    """
    component_name = file_info.get("component_name", "Page")
    node_id        = file_info.get("figma_node_id", "")

    # --- Récupérer le nœud page brut (pas nettoyé globalement) ---
    document_children = raw_tree.get("document", {}).get("children", [])
    page_node = None
    for canvas in document_children:
        page_node = _find_node_by_id(canvas, node_id)
        if page_node:
            break

    if not page_node:
        print(f"[Coder]   ATTENTION : nœud page '{node_id}' introuvable.")
        page_node = {}

    # --- Sections = enfants directs du nœud page ---
    raw_sections = [
        c for c in page_node.get("children", [])
        if isinstance(c, dict)
    ]

    if not raw_sections:
        print(f"[Coder]   ATTENTION : aucune section trouvée pour '{component_name}', génération simple.")
        return _generate_component(file_info, raw_tree, existing_components, llm)

    print(f"[Coder]   → {len(raw_sections)} section(s) détectée(s), génération section par section.")

    # --- Phase 1 : générer le JSX de chaque section ---
    sections_jsx: list[dict[str, str]] = []

    for idx, section in enumerate(raw_sections, 1):
        section_name = section.get("name", f"Section_{idx}")
        print(f"[Coder]     Section {idx}/{len(raw_sections)} : '{section_name}'...")

        # Nettoyer la section avant envoi
        cleaned_section = _clean_node(section)

        prompt = get_section_prompt(
            section_name=section_name,
            figma_json=cleaned_section,
            existing_components=existing_components,
        )
        jsx = _call_llm(llm, prompt)

        if jsx is None:
            print(f"[Coder]     ⚠️  Section '{section_name}' en échec — placeholder utilisé.")
            jsx = f'( <div className="section-{section_name.lower().replace(" ", "-")}"></div> )'

        jsx = _strip_fences(jsx)
        sections_jsx.append({"name": section_name, "jsx": jsx})
        print(f"[Coder]     ✅ Section '{section_name}' — {len(jsx)} chars")

    # --- Phase 2 : assembler la page ---
    print(f"[Coder]   → Assemblage de {component_name}...")

    prompt = get_assembly_prompt(
        component_name=component_name,
        sections_jsx=sections_jsx,
        existing_components=existing_components,
    )
    return _call_llm(llm, prompt)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def generate_code(project_path: Path, planning: dict[str, Any]) -> None:
    """Boucle principale de génération de code JSX."""
    print("\n[Coder] Démarrage de la génération (approche section-par-section pour les pages)...")

    # Chargement du JSON brut Figma
    raw_tree = _load_json(RAW_OUTPUT_FILE)
    if not raw_tree:
        print(f"[Coder] ERREUR FATALE : impossible de charger {RAW_OUTPUT_FILE}")
        return

    # Modèle LLM
    llm = get_llm(model=MODELS["default"])

    # Map nom_composant → chemin relatif (pour les imports)
    existing_components: dict[str, str] = {
        f["component_name"]: f["path"]
        for f in planning.get("files", [])
        if f.get("type") in ("component", "section")
    }

    generation_order: list[str] = planning.get("generation_order", [])
    total = len(generation_order)
    success_count = 0
    failed: list[str] = []

    for i, file_path_str in enumerate(generation_order, 1):
        print(f"\n[Coder] [{i}/{total}] {file_path_str}")

        # Métadonnées depuis le planning
        file_info = next(
            (f for f in planning["files"] if f["path"] == file_path_str), None
        )
        if not file_info:
            print("[Coder]   ERREUR : fichier absent du planning.")
            failed.append(file_path_str)
            continue

        file_type = file_info.get("type", "component")

        # --- Choix de la stratégie selon le type ---
        if file_type == "page":
            raw_code = _generate_page(file_info, raw_tree, existing_components, llm)
        else:
            raw_code = _generate_component(file_info, raw_tree, existing_components, llm)

        if raw_code is None:
            print(f"[Coder]   ❌ Échec définitif pour {file_path_str}")
            failed.append(file_path_str)
            continue

        # Nettoyage + écriture
        clean_code = _strip_fences(raw_code)
        full_path  = project_path / file_path_str
        _write_file(full_path, clean_code)
        print(f"[Coder]   ✅ Écrit → {full_path}")
        success_count += 1

    # Résumé
    print(f"\n[Coder] Terminé : {success_count}/{total} fichiers générés.")
    if failed:
        print(f"[Coder] Fichiers en échec ({len(failed)}) :")
        for f in failed:
            print(f"         - {f}")