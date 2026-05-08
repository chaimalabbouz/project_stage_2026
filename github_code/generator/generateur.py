""""
generateur.py
=============
Génère le code React TypeScript des composants et des pages.

STRATÉGIE : 2 LLMs séquentiels pour CHAQUE composant / section
  - LLM #1 (STRUCTURE) : produit le squelette JSX avec className="" vide
    et un attribut data-fname="..." sur chaque élément pour traçabilité.
    Il reçoit UNIQUEMENT la structure (props, layout, nodes list) — pas les styles.

  - LLM #2 (STYLE) : reçoit le squelette de #1 et les styles bruts.
    Il remplit les className="" avec du Tailwind arbitraire
    (ex: p-[16px], text-[#1a1a1a], gap-[8px]).

Python post-processe : retire data-fname, ajoute imports, écrit le fichier.

INPUTS :
  - architecture.json : définitions complètes des composants (props + styles)
  - sections.json    : pages avec placeholders d'instances + sections libres

OUTPUTS :
  - OUTPUT_DIR/my-app/src/components/*.tsx
  - OUTPUT_DIR/my-app/src/pages/*.tsx

Modèle utilisé : Qwen3-32B sur Groq (mode non-thinking pour éviter
le raisonnement dans la sortie).
"""

import json
import time
import re
from generator.style_converter import apply_styles_to_skeleton
from pathlib import Path
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import (
    GROQ_API_KEY,
    ARCHITECTURE_FILE,
    SECTIONS_OUTPUT_FILE,
    OUTPUT_DIR,
)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

QWEN_MODEL = "llama-3.3-70b-versatile"

PROJECT_DIR = OUTPUT_DIR / "my-app"
COMPONENTS_DIR = PROJECT_DIR / "src" / "components"
PAGES_DIR = PROJECT_DIR / "src" / "pages"

LLM_DELAY = 45
MAX_TOKENS_STRUCTURE = 5000
MAX_TOKENS_STYLE = 5000

# Suffixe ajouté à TOUS les system prompts pour désactiver le mode thinking
# de Qwen3. Sans ça, le modèle inclut un bloc <think>...</think> dans sa
# réponse, ce qui pollue le code généré.
NO_THINK_SUFFIX = "\n\n/no_think"


# ═══════════════════════════════════════════════════════════════
# PROMPT LLM #1 — SQUELETTE JSX (composants réutilisables)
# ═══════════════════════════════════════════════════════════════

STRUCTURE_SYSTEM_PROMPT = """
Tu es un expert React TypeScript.
Ton UNIQUE rôle est de générer la STRUCTURE JSX d un composant — sans styles.

Tu reçois :
- name : le nom exact du composant React
- kind : "standalone" ou "variant_set"
- props : la liste des props (name, figma_name, type, default, source)
- layout : "vertical" | "horizontal" | "grid" | "none"
- children_structure : description sémantique ordonnée des éléments
- children_tree : l arbre hiérarchique des nœuds Figma (type, name, layoutMode, children).
  Tu DOIS respecter cette hiérarchie dans ton JSX.
  Chaque FRAME avec un layoutMode dans l arbre doit devenir un <div> conteneur.
  Les enfants de ce FRAME doivent être imbriqués dedans.
  Utilise children_tree pour la STRUCTURE, et children_structure pour le contexte sémantique.
- imports : composants locaux et externes utilisés
- nodes : dict des nœuds stylables (figma_name → type)

Tu dois produire UNIQUEMENT le code TypeScript du composant, sans markdown,
sans explication, sans bloc de code.

RÈGLES STRICTES :
1. Utiliser EXACTEMENT les noms de props fournis (champ "name"), JAMAIS les renommer
2. Toutes les className DOIVENT être VIDES : className=""
3. Chaque élément JSX DOIT avoir data-fname="..." correspondant au figma_name
   Pour la racine : data-fname="__root__"
   Pour les autres : data-fname="figma_name_exact"
4. Si une prop a source "image" (son nom finit par "Url"),
   utiliser <img src={prop} alt="..." className="" data-fname="..." />
5. Si une prop a source "text" (type string), afficher {propName}
6. Si une prop est VARIANT (type union), NE PAS l afficher directement ;
   elle sert au style conditionnel. Ajouter data-variant-{propName}={propName}
   sur la racine.
7. Interface Props : toutes les props avec ? (optionnelles) et valeurs par défaut
8. Pour les imports locaux (imports.local) :
   import NomComposant from './NomComposant';
   et utiliser <NomComposant /> dans le JSX avec les props appropriées
9a) Pour les imports externes représentant des icônes :
- Utiliser react-icons si possible
- Ne pas limiter à une liste fixe
- Convertir le nom Figma en nom d’icône React valide (PascalCase)
- Choisir automatiquement une librairie appropriée si évident (ex: md, fa, hi)
- Exemple : "shopping_cart" → MdShoppingCart

9b) Si l’icône n’est pas identifiable avec confiance :
- Ne pas inventer une icône
- Générer un <div className="" data-fname="...">
10. export default function NomComposant(...)
11. Pas d import React nécessaire
12. Le JSX doit refléter la hiérarchie décrite dans children_structure
13. NE JAMAIS retourner "return null" ni un composant vide.
    Même si le composant semble simple (une seule image), génère le JSX complet.
    Un composant avec une seule prop image doit au minimum retourner :
    <div className="" data-fname="__root__">
      <img src={imageUrl} alt="" className="" data-fname="nom-du-noeud-image" />
    </div>
14. HIÉRARCHIE OBLIGATOIRE : si children_tree contient des FRAME imbriqués,
    tu DOIS créer des <div> imbriqués correspondants avec data-fname="nom-du-frame".
    Ne JAMAIS aplatir la structure. Un FRAME enfant d un autre FRAME = un <div> dans un <div>.
15. Tu DOIS générer un élément JSX pour CHAQUE nœud dans children_tree, sans exception.
    Ne jamais ignorer un nœud, même s il semble décoratif (VECTOR, RECTANGLE sans image).
    Un VECTOR → <div>, un RECTANGLE sans image → <div>.
EXEMPLE — composant avec hiérarchie (children_tree) :

Input :
{
  "name": "Testimonial",
  "kind": "standalone",
  "props": [
    {"name": "text", "figma_name": "review-text", "type": "string", "default": "Great product!", "source": "text"},
    {"name": "name", "figma_name": "user-name", "type": "string", "default": "John", "source": "text"},
    {"name": "role", "figma_name": "user-role", "type": "string", "default": "Customer", "source": "text"},
    {"name": "avatarUrl", "figma_name": "avatar", "type": "string", "default": "", "source": "image"}
  ],
  "layout": "vertical",
  "children_structure": ["Texte avis", "Section client avec avatar et infos"],
  "children_tree": {
    "name": "Testimonial",
    "layoutMode": "VERTICAL",
    "children": [
      {"type": "TEXT", "name": "review-text"},
      {"type": "FRAME", "name": "Customer", "layoutMode": "HORIZONTAL", "children": [
        {"type": "RECTANGLE", "name": "avatar", "hasImageFill": true},
        {"type": "FRAME", "name": "Info", "layoutMode": "VERTICAL", "children": [
          {"type": "TEXT", "name": "user-name"},
          {"type": "TEXT", "name": "user-role"}
        ]}
      ]}
    ]
  },
  "imports": {"local": [], "external": []},
  "nodes": {"review-text": {"type": "TEXT"}, "Customer": {"type": "FRAME"}, "avatar": {"type": "RECTANGLE"}, "Info": {"type": "FRAME"}, "user-name": {"type": "TEXT"}, "user-role": {"type": "TEXT"}}
}

Output :
interface TestimonialProps {
  text?: string;
  name?: string;
  role?: string;
  avatarUrl?: string;
}

export default function Testimonial({ text = "Great product!", name = "John", role = "Customer", avatarUrl = "" }: TestimonialProps) {
  return (
    <div className="" data-fname="__root__">
      <p className="" data-fname="review-text">{text}</p>
      <div className="" data-fname="Customer">
        <img src={avatarUrl} alt={name} className="" data-fname="avatar" />
        <div className="" data-fname="Info">
          <span className="" data-fname="user-name">{name}</span>
          <span className="" data-fname="user-role">{role}</span>
        </div>
      </div>
    </div>
  );
}
""".strip() + NO_THINK_SUFFIX


# ═══════════════════════════════════════════════════════════════
# PROMPT LLM #2 — STYLES TAILWIND
# ═══════════════════════════════════════════════════════════════

STYLE_SYSTEM_PROMPT = """
Tu es un expert Tailwind CSS.
Tu reçois du code React TypeScript avec des className DÉJÀ PRÉ-REMPLIS
par un système automatique, et des data-fname="...".
Tu reçois aussi les styles Figma bruts (root_styles + nodes_styles).

Ton rôle est de VÉRIFIER et COMPLÉTER les className existants :
1. VÉRIFIER que les classes pré-remplies sont correctes
2. COMPLÉTER si des styles Figma n ont pas été convertis
3. CORRIGER si des classes sont erronées ou manquantes
4. Gérer les cas complexes (variants clsx, responsive, cas ambigus)
Ne SUPPRIME PAS les classes existantes sauf si elles sont fausses.
Si tout est correct, retourne le code INCHANGÉ.

RÉFÉRENCE des mappings Tailwind (pour vérification) :

LAYOUT :
  layoutMode VERTICAL -> flex flex-col
  layoutMode HORIZONTAL -> flex flex-row
  primaryAxisAlignItems CENTER -> justify-center
  primaryAxisAlignItems SPACE_BETWEEN -> justify-between
  primaryAxisAlignItems MAX -> justify-end
  primaryAxisAlignItems MIN -> justify-start
  counterAxisAlignItems CENTER -> items-center
  counterAxisAlignItems MIN -> items-start
  counterAxisAlignItems MAX -> items-end
  itemSpacing N -> gap-[Npx]
  layoutWrap WRAP -> flex-wrap

PADDING :
  Si les 4 côtés sont égaux -> p-[Npx]
  Si left=right ET top=bottom -> px-[Lpx] py-[Tpx]
  Sinon -> pl-[Lpx] pr-[Rpx] pt-[Tpx] pb-[Bpx]

SIZING :
  layoutSizingHorizontal FILL -> w-full
  layoutSizingHorizontal HUG -> w-fit
  layoutSizingHorizontal FIXED + width -> w-[Wpx]
  layoutSizingVertical FILL -> h-full
  layoutSizingVertical HUG -> h-fit
  layoutSizingVertical FIXED + height -> h-[Hpx]
  layoutGrow 1 -> flex-1

COULEURS :
  fills SOLID avec visible != false -> bg-[#hex]
  fills SOLID avec visible: false -> IGNORER
  TEXT avec color.hex -> text-[#hex]

TYPOGRAPHIE :
  fontSize N -> text-[Npx]
  fontWeight 400 -> font-normal
  fontWeight 500 -> font-medium
  fontWeight 600 -> font-semibold
  fontWeight 700 -> font-bold
  fontFamily "Nom" -> font-['Nom']
  textAlignHorizontal CENTER -> text-center
  lineHeightPx N -> leading-[Npx]
  letterSpacing N (si != 0) -> tracking-[Npx]

BORDURES :
  cornerRadius N -> rounded-[Npx]
  rectangleCornerRadii [TL,TR,BR,BL] -> rounded-tl-[TLpx] etc.
  strokeWeight N + strokes SOLID visible -> border-[Npx] border-[#hex]

EFFETS :
  DROP_SHADOW -> shadow-[Xpx_Ypx_Rpx_rgba(r,g,b,A)]

OPACITY :
  opacity N (si != 1) -> opacity-[N]

IMAGE :
  fills IMAGE + scaleMode FILL -> object-cover
  fills IMAGE + scaleMode FIT -> object-contain

CLIPPING :
  clipsContent true -> overflow-hidden

VARIANT CONDITIONNEL (si styles_by_variant est fourni) :
  Importer clsx en haut : import clsx from 'clsx';
  Utiliser : className={clsx("classes-de-base", { "classe-variante": condition })}

RAPPEL FINAL : Retourne UNIQUEMENT le code TypeScript modifié.
Pas de markdown, pas de backticks, pas d explication, pas d analyse.
Juste le code, rien d autre.
""".strip() + NO_THINK_SUFFIX


# ═══════════════════════════════════════════════════════════════
# PROMPT LLM #3 — SECTIONS LIBRES (structure + style en un pass)
# ═══════════════════════════════════════════════════════════════

SECTION_SYSTEM_PROMPT = """
Tu es un expert React TypeScript et Tailwind CSS.
Tu reçois une SECTION de page Figma (un FRAME libre) avec :
- Son arbre de nœuds (type, name, characters, styles à chaque nœud)
- Les appels JSX des composants réutilisables déjà construits (jsx_calls)
- La liste des imports nécessaires

Tu dois produire le JSX COMPLET de la section AVEC les classes Tailwind,
en un seul bloc. Pas de fonction, pas d interface, juste le JSX.

Tu dois produire UNIQUEMENT le JSX, sans markdown, sans explication,
sans bloc de code.

RÈGLES :
1. Pour chaque nœud libre (FRAME, TEXT, RECTANGLE, etc.) :
   - Convertir en HTML approprié (div, span, p, img, etc.)
   - Appliquer les classes Tailwind depuis le champ "styles" du nœud
   - Mêmes règles de conversion Tailwind que pour les composants :
     layoutMode -> flex flex-col/flex-row
     padding -> p-[Npx] / px-[Npx] py-[Npx]
     itemSpacing -> gap-[Npx]
     fills SOLID -> bg-[#hex]
     fontSize -> text-[Npx]
     fontWeight -> font-normal/medium/semibold/bold
     cornerRadius -> rounded-[Npx]
     effects DROP_SHADOW -> shadow-[...]
     etc.

2. Pour chaque __COMPONENT_PLACEHOLDER__ :
   Utiliser le jsx_call TEL QUEL, sans ajouter de className ni wrapper

3. Pour les nœuds TEXT avec "characters" :
   Afficher le texte directement (pas de prop, c est du contenu statique)

4. Pour les RECTANGLE/ELLIPSE avec fill IMAGE :
   Utiliser <img src="/placeholder.jpg" alt="..." className="..." />

5. Respecter la hiérarchie parent-enfant de l arbre
6. POSITIONNEMENT ABSOLU
   Si un nœud a styles._positioning = "absolute", c est un conteneur absolu :
   → Ajouter "relative" à son className
   Si un nœud a styles._position avec top et left :
   → Ajouter "absolute top-[Tpx] left-[Lpx]" à son className
   Exemple :
   - Parent avec _positioning: "absolute" → className="relative w-[584px] h-[273px]"
   - Enfant avec _position: {top: 6.5, left: 18} → className="absolute top-[6.5px] left-[18px] ..."
7. SIMPLIFICATION DES WRAPPERS
- Si un FRAME ou GROUP n’a pas de styles significatifs, ne pas générer de <div>
- Si un FRAME ou GROUP contient un seul enfant utile, retourner directement l’enfant (pas de wrapper)
- Ne jamais créer de div vide ou inutile
8. CONTRAINTES STRICTES
- Ne jamais créer plusieurs niveaux de <div> inutiles
- Ne jamais générer <div><div><div>...</div></div></div> sans raison
EXEMPLE :

Input :
{
  "section_tree": {
    "name": "HeroSection",
    "type": "FRAME",
    "styles": {"layout": {"layoutMode": "VERTICAL", "padding": {"paddingTop": 40, "paddingBottom": 40}, "itemSpacing": 24}},
    "children": [
      {"type": "TEXT", "name": "hero-title", "characters": "Welcome", "styles": {"fontSize": 48, "fontWeight": 700, "color": {"hex": "#1a1a1a"}}},
      {"type": "__COMPONENT_PLACEHOLDER__", "jsx_call": "<Button label=\\"Click me\\" />"}
    ]
  },
  "imports": ["Button"]
}

Output :
<div className="flex flex-col py-[40px] gap-[24px]">
  <h1 className="text-[48px] font-bold text-[#1a1a1a]">Welcome</h1>
  <Button label="Click me" />
</div>
""".strip() + NO_THINK_SUFFIX


# ═══════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════

def _call_llm(system_prompt: str, user_content: str, llm: ChatGroq,
              max_tokens: int = 4096) -> str:
    """Appel LLM avec retry sur rate-limit."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages, max_tokens=max_tokens)
            raw = response.content.strip()

            # Retirer les blocs <think>...</think> si Qwen3 les inclut malgré /no_think
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            # Retirer les fences markdown si le LLM en met
            if raw.startswith("```"):
                lines = raw.split("\n")
                # Trouver la dernière ligne ```
                end_idx = len(lines) - 1
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip().startswith("```"):
                        end_idx = i
                        break
                raw = "\n".join(lines[1:end_idx]).strip()

            time.sleep(LLM_DELAY)
            return raw
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait_time = (attempt + 1) * 30
                print(f"  [RATE LIMIT] Attente {wait_time}s ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError("Rate limit : max retries atteint")


def _remove_data_fname(code: str) -> str:
    """Retire tous les data-fname="..." et data-variant-*={...} du code final."""
    code = re.sub(r'\s+data-fname="[^"]*"', '', code)
    code = re.sub(r'\s+data-fname=\{[^}]*\}', '', code)
    code = re.sub(r'\s+data-variant-[a-zA-Z]+=\{[^}]*\}', '', code)
    return code


def _build_prop_string(key: str, value) -> str:
    """Formate une prop pour le JSX : key={value} ou key="value"."""
    if isinstance(value, bool):
        return f"{key}={{{str(value).lower()}}}"
    elif isinstance(value, (int, float)):
        return f"{key}={{{value}}}"
    else:
        safe_value = str(value).replace('"', '\\"').replace("\n", " ")
        return f'{key}="{safe_value}"'


def _build_component_jsx(react_name: str, props_values: dict) -> str:
    """Construit l'appel JSX d'un composant avec ses props."""
    if not props_values:
        return f"<{react_name} />"
    parts = [_build_prop_string(k, v) for k, v in props_values.items()]
    return f"<{react_name} {' '.join(parts)} />"


def _ensure_imports(code: str) -> str:
    """Ajoute import React et clsx si nécessaire."""
    lines_to_add = []

    if "import React" not in code and "from 'react'" not in code:
        lines_to_add.append("import React from 'react';")

    if "clsx(" in code and "import clsx" not in code:
        lines_to_add.append("import clsx from 'clsx';")

    if lines_to_add:
        code = "\n".join(lines_to_add) + "\n\n" + code

    return code


def _sanitize_component_name(name: str) -> str:
    """Convertit un nom Figma en PascalCase valide pour un fichier/composant."""
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    cleaned = "".join(p[0].upper() + p[1:] for p in parts if p)
    return cleaned or "Component"


def _sanitize_page_name(name: str) -> str:
    """Convertit un nom de page Figma en PascalCase valide."""
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    cleaned = "".join(p[0].upper() + p[1:] for p in parts if p)
    return cleaned or "Page"


# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION D'UN COMPOSANT RÉUTILISABLE (LLM #1 + LLM #2)
# ═══════════════════════════════════════════════════════════════

def _generate_component(arch_entry: dict, llm: ChatGroq) -> str:
    """Génère le code d'un composant avec LLM #1 (structure) + styles déterministes."""
    name = arch_entry["name"]
    architecture = arch_entry.get("architecture", {})
    styles = arch_entry.get("styles", {})
    kind = arch_entry.get("kind", "standalone")
    imports = arch_entry.get("imports", {"local": [], "external": []})

    # ─── LLM #1 : STRUCTURE ───
    structure_payload = {
        "name": name,
        "kind": kind,
        "props": [
            {
                "name": p["name"],
                "figma_name": p["figma_name"],
                "type": p["type"],
                "default": p.get("default", ""),
                "source": p.get("source", "text"),
            }
            for p in architecture.get("props", [])
        ],
        "layout": architecture.get("layout", "none"),
        "children_structure": architecture.get("children_structure", []),
        "children_tree": architecture.get("children_tree", {}),
        "imports": imports,
        "nodes": {
            figma_name: {"type": node_data.get("type", "FRAME")}
            for figma_name, node_data in styles.get("nodes", {}).items()
        },
    }

    payload_str = json.dumps(structure_payload, ensure_ascii=False, indent=None)
    print(f"  [LLM #1 structure] envoi {len(payload_str)} chars...")

    jsx_skeleton = _call_llm(
        STRUCTURE_SYSTEM_PROMPT,
        f"Génère le composant '{name}' :\n\n{payload_str}",
        llm,
        max_tokens=MAX_TOKENS_STRUCTURE,
    )

    print(f"  [LLM #1 structure] reçu {len(jsx_skeleton)} chars")

    # ─── ÉTAPE 2 : Styles déterministes ───
    pre_styled = apply_styles_to_skeleton(jsx_skeleton, styles)
    print(f"  [DETERMINISTIC] className pré-remplis")

    # ─── Post-process Python ───
    final_code = _remove_data_fname(pre_styled)
    final_code = _ensure_imports(final_code)

    return final_code


def _prepare_section_tree(section_data: dict) -> dict:
    """Prépare l'arbre de la section :
    - Remplace les __COMPONENT_PLACEHOLDER__ par leur jsx_call
    - Garde les styles, id et interactions à chaque nœud
    """
    if not isinstance(section_data, dict):
        return section_data

    if section_data.get("type") == "__COMPONENT_PLACEHOLDER__":
        react_name = section_data.get("react_component_name", "Component")
        props_values = section_data.get("props_values", {})

        result = {
            "type": "__COMPONENT_PLACEHOLDER__",
            "jsx_call": _build_component_jsx(react_name, props_values),
        }

        for key in ("id", "styles", "interaction"):
            if key in section_data:
                result[key] = section_data[key]

        return result

    cleaned = {}

    for key in ("id", "name", "type", "characters", "styles", "interaction"):
        if key in section_data:
            cleaned[key] = section_data[key]

    if "children" in section_data and isinstance(section_data["children"], list):
        cleaned["children"] = [
            _prepare_section_tree(child)
            for child in section_data["children"]
            if isinstance(child, dict)
        ]

    return cleaned

def _collect_section_imports(section_child: dict) -> list[str]:
    """Collecte les noms React des composants utilisés dans une section."""
    names = set()
    for inst in section_child.get("nested_instances", []):
        react_name = inst.get("react_component_name")
        if react_name:
            names.add(react_name)
    return sorted(names)


def _generate_section_jsx(
    section_data: dict,
    nested_instances: list,
    route_by_node_id: dict,
) -> str:
    """Génère le JSX d'une section libre de manière déterministe."""
    from generator.style_converter import generate_section_jsx_deterministic

    section_name = section_data.get("name", "Section")
    section_tree = _prepare_section_tree(section_data)

    jsx = generate_section_jsx_deterministic(
        section_tree,
        route_by_node_id=route_by_node_id,
    )

    print(f"    [DETERMINISTIC section] {section_name} ({len(jsx)} chars)")
    return jsx.strip()
# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION DES COMPOSANTS
# ═══════════════════════════════════════════════════════════════

def _collect_all_used_components(sections_data: dict) -> set:
    """Parcourt toutes les pages et collecte les noms React utilisés."""
    used = set()
    for page in sections_data.get("pages", []):
        for child in page.get("ordered_children", []):
            if child["kind"] == "instance":
                used.add(child["data"].get("react_component_name"))
            elif child["kind"] == "section":
                for inst in child.get("nested_instances", []):
                    used.add(inst.get("react_component_name"))
    used.discard(None)
    return used


def generate_components(architecture: dict, llm: ChatGroq) -> None:
    """Génère les composants réutilisables dans l'ordre topologique."""
    print("\n[generateur] === Génération des composants ===")
    COMPONENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Utiliser generation_order si disponible, sinon l'ordre par défaut
    generation_order = architecture.get("generation_order", [])
    components = architecture.get("components", [])

    # Indexer les composants par nom
    comp_by_name = {}
    for comp in components:
        comp_name = comp.get("name")
        if comp_name:
            comp_by_name[comp_name] = comp

    # Déterminer l'ordre de génération
    if generation_order:
        ordered_names = generation_order
    else:
        ordered_names = [c.get("name") for c in components if c.get("name")]

    generated = 0
    skipped = 0

    for name in ordered_names:
        
        comp = comp_by_name.get(name)
        if not comp:
            print(f"[generateur] WARN : '{name}' dans generation_order mais absent des components")
            continue

        print(f"\n[generateur] Composant : {name}")
        try:
            code = _generate_component(comp, llm)

            # Nom de fichier sécurisé
            file_name = _sanitize_component_name(name)
            file_path = COMPONENTS_DIR / f"{file_name}.tsx"
            file_path.write_text(code, encoding="utf-8")

            generated += 1
            print(f"[generateur] OK → {file_name}.tsx ({len(code)} chars)")
        except Exception as e:
            print(f"[generateur] ERREUR pour {name} : {e}")

    print(f"\n[generateur] {generated} composants générés")

# ═══════════════════════════════════════════════════════════════
# ROUTING / INTERACTIONS
# ═══════════════════════════════════════════════════════════════
def _route_from_page_name(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    slug = "-".join(p.lower() for p in parts)
    return "/" if slug in ("home", "accueil", "index") else f"/{slug}"


def _html_id_from_figma_id(figma_id: str) -> str:
    return "figma-" + str(figma_id).replace(":", "-").replace(";", "-")


def _wrap_with_interaction(jsx: str, interaction: dict | None, route_by_node_id: dict) -> str:
    if not interaction:
        return jsx

    if interaction.get("type") == "navigate":
        target_id = interaction.get("target_node_id")
        route = route_by_node_id.get(target_id)

        if route:
            return f'<Link to="{route}">{jsx}</Link>'

    return jsx




def _tree_has_interaction_type(node: dict, interaction_type: str) -> bool:
    if not isinstance(node, dict):
        return False

    interaction = node.get("interaction", {})
    if interaction.get("type") == interaction_type:
        return True

    for child in node.get("children", []):
        if _tree_has_interaction_type(child, interaction_type):
            return True

    return False

def _collect_node_ids(node: dict, ids: set) -> None:
    if not isinstance(node, dict):
        return

    node_id = node.get("id")
    if node_id:
        ids.add(node_id)

    for child in node.get("children", []):
        _collect_node_ids(child, ids)


def _build_route_by_node_id(sections_data: dict) -> dict:
    route_by_node_id = {}

    for i, page in enumerate(sections_data.get("pages", [])):
        safe_name = _sanitize_page_name(page.get("page_name", "Page"))
        route = "/" if i == 0 else _route_from_page_name(safe_name)

        if page.get("page_id"):
            route_by_node_id[page["page_id"]] = route

        for child in page.get("ordered_children", []):
            ids = set()
            _collect_node_ids(child.get("data", {}), ids)

            for node_id in ids:
                route_by_node_id[node_id] = route

    return route_by_node_id    
# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION DES PAGES
# ═══════════════════════════════════════════════════════════════

def _generate_page(page: dict, llm: ChatGroq = None) -> tuple[str, str, int, int]:
    """Génère le code d'une page entière.
    Retourne (file_name, code, llm_calls, imports_count).
    """
    page_name = page["page_name"]
    file_name = _sanitize_page_name(page_name)

    print(f"\n[generateur] Page : {file_name}.tsx")

    ordered_children = page.get("ordered_children", [])
    ordered_children.sort(key=lambda c: c.get("order_index", 0))

    route_by_node_id = page.get("_route_by_node_id", {})

    imports_needed = set()
    needs_link = False
    needs_overlay_state = False

    for child in ordered_children:
        data = child.get("data", {})
        interaction = data.get("interaction", {})

        if interaction.get("type") == "navigate":
            needs_link = True

        if interaction.get("type") in ("open_overlay", "close_overlay"):
            needs_overlay_state = True

        if child["kind"] == "instance":
            imports_needed.add(data.get("react_component_name"))

        elif child["kind"] == "section":
            if _tree_has_interaction_type(data, "navigate"):
                needs_link = True

            if (
                _tree_has_interaction_type(data, "open_overlay")
                or _tree_has_interaction_type(data, "close_overlay")
            ):
                needs_overlay_state = True

            for inst in child.get("nested_instances", []):
                imports_needed.add(inst.get("react_component_name"))

                inst_interaction = inst.get("interaction", {})
                if inst_interaction.get("type") == "navigate":
                    needs_link = True
                if inst_interaction.get("type") in ("open_overlay", "close_overlay"):
                    needs_overlay_state = True

    imports_needed.discard(None)

    jsx_blocks = []
    overlay_blocks = []
    llm_calls = 0

    for child in ordered_children:
        kind = child["kind"]
        data = child["data"]

        if kind == "instance":
            react_name = data.get("react_component_name", "Component")
            props_values = data.get("props_values", {})

            jsx = _build_component_jsx(react_name, props_values)
            jsx = _wrap_with_interaction(
                jsx,
                data.get("interaction"),
                route_by_node_id,
            )

            jsx_blocks.append("        " + jsx)
            print(f"  [INSTANCE]  <{react_name} /> (direct)")

        elif kind == "section":
            section_name = data.get("name", "Section")
            nested = child.get("nested_instances", [])

            print(f"  [SECTION]   {section_name} → génération déterministe...")

            try:
                jsx = _generate_section_jsx(data, nested, route_by_node_id)

                section_id = data.get("id")
                if section_id:
                    html_id = _html_id_from_figma_id(section_id)
                    jsx = f'<div id="{html_id}">\n{jsx}\n</div>'

                jsx = _wrap_with_interaction(
                    jsx,
                    data.get("interaction"),
                    route_by_node_id,
                )

                indented = "\n".join(
                    f"        {line}" if line.strip() else ""
                    for line in jsx.split("\n")
                )

                jsx_blocks.append(
                    f"        {{/* Section: {section_name} */}}\n{indented}"
                )

                llm_calls += 1
                print(f"  [SECTION]   OK — {section_name} ({len(jsx)} chars)")

            except Exception as e:
                print(f"  [ERREUR]    {section_name} : {e}")
                jsx_blocks.append(
                    f"        {{/* ERREUR section {section_name} : {e} */}}"
                )

    import_lines = []

    if needs_link:
        import_lines.append("import { Link } from 'react-router-dom';")

    for name in sorted(imports_needed):
        safe_name = _sanitize_component_name(name)
        import_lines.append(f"import {safe_name} from '../components/{safe_name}';")

    imports_str = "\n".join(import_lines)
    if imports_str:
        imports_str = "\n" + imports_str

    jsx_body = "\n\n".join(jsx_blocks) if jsx_blocks else "        {/* Page vide */}"
    overlays_body = "\n\n".join(overlay_blocks)

    page_styles = page.get("page_styles", {})
    page_bg = ""
    if "backgroundColor" in page_styles:
        page_bg = f' bg-[{page_styles["backgroundColor"]}]'

    page_width = int(page_styles.get("width", 1440))
    page_height = int(page_styles.get("height", 1024))

    overlay_state_line = (
        '  const [activeOverlay, setActiveOverlay] = useState<string | null>(null);\n'
        if needs_overlay_state or overlay_blocks
        else ""
    )

    page_code = f"""import React, {{ useEffect, useState }} from 'react';{imports_str}

export default function {file_name}() {{
  const [scale, setScale] = useState(1);
{overlay_state_line}
  useEffect(() => {{
    const updateScale = () => {{
      const screenWidth = window.innerWidth;
      const designWidth = {page_width};
      const newScale = Math.min(1, screenWidth / designWidth);
      setScale(newScale);
    }};

    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }}, []);

  return (
    <div
      className="w-full overflow-x-hidden flex justify-center{page_bg}"
      style={{{{ minHeight: `${{{page_height} * scale}}px` }}}}
    >
      <div
        className="relative flex-shrink-0"
        style={{{{
          width: `{page_width}px`,
          height: `{page_height}px`,
          transform: `scale(${{scale}})`,
          transformOrigin: 'top center',
        }}}}
      >
{jsx_body}

{overlays_body}
      </div>
    </div>
  );
}}
"""

    return file_name, page_code, llm_calls, len(imports_needed)

def generate_pages(sections_data: dict, llm: ChatGroq) -> None:
    """Génère tous les fichiers de pages."""
    print("\n[generateur] === Génération des pages ===")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    route_by_node_id = _build_route_by_node_id(sections_data)

    all_pages = []
    for i, page in enumerate(sections_data.get("pages", [])):
        safe_name = _sanitize_page_name(page.get("page_name", "Page"))
        route = "/" if i == 0 else _route_from_page_name(safe_name)

        all_pages.append({
            "page_id": page.get("page_id"),
            "page_name": page.get("page_name"),
            "name": safe_name,
            "route": route,
        })

    for page in sections_data.get("pages", []):
        try:
            page["_all_pages"] = all_pages
            page["_route_by_node_id"] = route_by_node_id

            file_name, page_code, llm_calls, imports_count = _generate_page(page, llm)

            file_path = PAGES_DIR / f"{file_name}.tsx"
            file_path.write_text(page_code, encoding="utf-8")

            print(f"\n[generateur] OK → {file_name}.tsx")
            print(f"  Imports  : {imports_count} composants")
            print(f"  Sections : {llm_calls} appels LLM")

        except Exception as e:
            print(f"[generateur] ERREUR page '{page.get('page_name')}' : {e}")

# ═══════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

def run_generateur() -> None:
    print("\n[generateur] Chargement des fichiers...")

    with open(ARCHITECTURE_FILE, "r", encoding="utf-8") as f:
        architecture = json.load(f)
    with open(SECTIONS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        sections_data = json.load(f)

    llm = ChatGroq(
        model=QWEN_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0.6,
        max_tokens=MAX_TOKENS_STYLE,
        model_kwargs={
            "top_p": 0.95,
        },
    )

    all_component_names = [
        c.get("name") for c in architecture.get("components", [])
        if c.get("name")
    ]
    print(f"[generateur] {len(all_component_names)} composants trouvés dans architecture.json : {sorted(all_component_names)}")

    generate_components(architecture, llm)
    # ─── Étape 2 : pages ───
    generate_pages(sections_data, llm)

    print("\n[generateur] === Génération terminée ===")
    print(f"[generateur] Projet → {PROJECT_DIR}")


def run_generateur_page(page_name: str) -> None:
    """Régénère une seule page par son nom (utile pour debug)."""
    print(f"\n[generateur] Régénération de la page '{page_name}'...")

    with open(SECTIONS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        sections_data = json.load(f)

    llm = ChatGroq(
        model=QWEN_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0.6,
        max_tokens=MAX_TOKENS_STYLE,
        model_kwargs={
            "top_p": 0.95,
        },
    )

    matching = [
        p for p in sections_data.get("pages", [])
        if p["page_name"] == page_name
    ]

    if not matching:
        print(f"[generateur] Page '{page_name}' non trouvée.")
        return

    route_by_node_id = _build_route_by_node_id(sections_data)

    all_pages = []
    for i, p in enumerate(sections_data.get("pages", [])):
        safe_name = _sanitize_page_name(p.get("page_name", "Page"))
        route = "/" if i == 0 else _route_from_page_name(safe_name)

        all_pages.append({
            "page_id": p.get("page_id"),
            "page_name": p.get("page_name"),
            "name": safe_name,
            "route": route,
        })

    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    for page in matching:
        page["_all_pages"] = all_pages
        page["_route_by_node_id"] = route_by_node_id

        file_name, page_code, _, _ = _generate_page(page, llm)

        file_path = PAGES_DIR / f"{file_name}.tsx"
        file_path.write_text(page_code, encoding="utf-8")

        print(f"[generateur] OK → {file_name}.tsx")

def run_generateur_pages_only() -> None:
    """Régénère seulement les pages/sections, sans toucher aux composants."""
    print("\n[generateur] Régénération des pages uniquement...")

    with open(SECTIONS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        sections_data = json.load(f)

    generate_pages(sections_data, None)

    print("\n[generateur] === Pages régénérées ===")