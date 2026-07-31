

import json
import time
import re

from pathlib import Path
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import (
    
    ARCHITECTURE_FILE,
    SECTIONS_OUTPUT_FILE,
    OUTPUT_DIR,
    MISTRAL_API_KEY,
    CODESTRAL_MODEL,
)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════



PROJECT_DIR = OUTPUT_DIR / "my-app"
COMPONENTS_DIR = PROJECT_DIR / "src" / "components"
PAGES_DIR = PROJECT_DIR / "src" / "pages"

LLM_DELAY = 45




# ═══════════════════════════════════════════════════════════════
# PROMPT LLM #1 — SQUELETTE JSX (composants réutilisables)
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Tu es un expert React + TypeScript + Tailwind CSS.

Ton rôle : générer UN SEUL fichier de composant React fidèle au design Figma,
en utilisant EXCLUSIVEMENT les données fournies dans le payload.

RÈGLES :
1. SOURCE UNIQUE DE VÉRITÉ : utilise UNIQUEMENT les données du payload.
2. FIDÉLITÉ VISUELLE : Tailwind arbitraire (bg-[#hex], p-[Xpx], etc).
3. STRUCTURE : respecte children_tree.
4. PROPS : interface TypeScript exacte depuis le payload.
5. IMPORTS : utilise imports.local (noms PropreCase).
6. SORTIE : code .tsx pur, export default obligatoire.
7. COMPOSANTS IMPORTÉS :
Si component_usage existe, utilise STRICTEMENT props_mapping pour appeler les composants locaux.

IMPORTANT :
- Si props_mapping contient des props, passe uniquement ces props.
- Si props_mapping est vide {}, appelle le composant sans aucune prop.
- N'invente jamais de props comme className, text, label, children, style ou color.
- Ne déduis jamais une prop depuis les styles Figma.
- Le parent place le composant, mais ne modifie pas son API interne.
8. IMPORT SANS PROPS :
Si un composant local importé a props_mapping: {}, il doit être appelé sans props.
Exemple : <IconLinkedin />
Interdit : <IconLinkedin color={...} />, <IconLinkedin className={...} />
9. VARIANTS :
Quand un composant local importé possède une prop de type VARIANT dans component_usage.props_mapping,
passe cette prop au composant enfant avec la valeur exacte donnée.

Exemple :
props_mapping: { "color": "White" }
=> <SocialButton color="White" />

Si props_mapping est vide {}, appelle le composant sans props.

Ne transmets jamais une variante à un sous-enfant.
Ne transforme jamais une couleur, un style ou un fill Figma en prop React si ce n'est pas dans props_mapping.
10. INSTANCE LOCALE = COMPOSANT ATOMIQUE :
Quand un noeud children_tree est une INSTANCE correspondant à un composant local importé,
tu dois le rendre comme un composant React autonome.

N'utilise JAMAIS ses children Figma comme children JSX.
Exemple correct :
<SocialButton color="White" />

Exemple interdit :
<SocialButton color="White">
  <IconLinkedin />
</SocialButton>

Les children internes d'une INSTANCE locale appartiennent déjà au composant importé.
Le parent doit seulement placer l'instance et lui passer les props_mapping.
11. IMPORTS :
imports.local est une donnée JSON, pas un chemin.

Toujours utiliser :
import ComponentName from './ComponentName';

Jamais :
import ... from 'imports.local/...';

Importer seulement les composants utilisés directement dans le fichier.
Ne pas importer les enfants internes d'un composant.
12. INTERACTIONS :
Si "interactions" existe dans le payload :
- Si interactions.root n'est pas vide → ajouter une prop `onClick?: () => void` 
  à l'interface, et la mettre sur l'élément racine du composant.
- Si interactions.nodes contient des entrées → ajouter une prop optionnelle 
  `on<NomDuNoeud>Click?: () => void` pour chaque clé, et la mettre 
  sur l'élément correspondant.

Exemple si interactions.nodes = {"Projects": [...], "Resume": [...]} :
  Props : onProjectsClick?: () => void; onResumeClick?: () => void;
  Usage : <span onClick={onProjectsClick}>...</span>
          <span onClick={onResumeClick}>...</span>

Ne PAS hardcoder de navigation ou route. Juste exposer les props.
IMPORTANT : Si une clé de interactions.nodes correspond à une INSTANCE 
de composant local importé (Button, Card, etc.), il faut :
- exposer la prop `on<Nom>Click?: () => void`
- la passer au composant via sa prop onClick

Exemple si interactions.nodes = {"Button": [...]} :
  Props : onButtonClick?: () => void;
  Usage : <Button ... onClick={onButtonClick} />


13. PROPS TOUJOURS OPTIONNELLES AVEC VALEUR PAR DÉFAUT :
Une instance Figma n'override QUE certaines props ; les autres gardent
leur valeur par défaut du composant. TOUTES les props doivent être
optionnelles (`?`) avec une valeur par défaut dans la déstructuration,
correspondant à architecture.props[].default si présent, sinon selon
le type (boolean→false, string→"", number→0, union→première valeur
listée, ReactNode→null). Exception : les callbacks (onClick, on<X>Click)
restent optionnels sans valeur par défaut obligatoire.

13bis. SI `default` EST ABSENT pour une prop, applique STRICTEMENT le
tableau ci-dessus selon le type. Ne jamais improviser une valeur
"logique" au jugé — le choix doit être entièrement déterminé par le
type déclaré, jamais par une intuition sur ce composant précis.

13ter. PROPS DE SURCHARGE ("change<X>") : TOUJOURS VIDES PAR DÉFAUT
Une prop dont le nom commence par "change" (changeText, changeLeftIcon,
changeRightIcon, etc.) est une SURCHARGE CONDITIONNELLE, pas un texte
de base. Elle doit avoir comme valeur par défaut "" (string) ou null
(ReactNode) — IGNORE toute valeur `default` non-vide trouvée dans le
payload pour ce type de prop, même si le payload en indique une.
Le texte/icône réellement affiché par défaut vient UNIQUEMENT de la
prop qui ne commence PAS par "change" (buyNow, label, title...), avec
sa vraie valeur par défaut Figma.

Exemple correct :
  changeText = "",
  buyNow = "Buy Now",
Exemple INTERDIT :
  changeText = "Buy Now",  // rend buyNow inatteignable via changeText || buyNow

14. ICÔNES : JAMAIS D'IMPORT EXTERNE
Interdiction absolue d'importer un package d'icônes (@tabler/icons,
@solar-ui/icons, lucide-react, react-icons, ou autre). Pour chaque
icône Figma référencée, génère un SVG inline minimal (<svg>...</svg>,
~16-24px, currentColor) qui représente au mieux l'icône visée par son
nom, directement dans le composant. Aucun import supplémentaire n'est
autorisé pour ça, aucune exception.

15. FEEDBACK VISUEL AU CLIC (hover/active)
Figma n'expose généralement pas d'état hover/pressed séparé dans les
données du payload (ce sont des variants non capturés par l'extraction).
Pour compenser, tout élément possédant un `onClick` (bouton, lien, ou
tout élément interactif rendu par la règle 12) DOIT recevoir en plus
de ses classes normales :
- Si l'élément a un fond coloré (bg-[#hex]) : ajoute `hover:opacity-90
  active:opacity-75 transition-opacity`.
- Si l'élément n'a PAS de fond (texte seul, icône seule) : ajoute
  `hover:opacity-70 active:opacity-50 transition-opacity`.
- Ajoute toujours `cursor-pointer` sur ces éléments.

C'est un fallback UNIFORME et déterministe (opacité), pas une tentative
de deviner une couleur de hover différente à chaque fois — n'invente
jamais une nouvelle couleur bg-[#hex2] pour l'état hover.

""".strip()






# ═══════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════

def _call_llm(llm, system_prompt: str, user_content: str) -> str:
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages)
            time.sleep(LLM_DELAY)
            return response.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "limit" in err:
                wait = (attempt + 1) * 5
                print(f"  [RATE LIMIT] Attente {wait}s ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Rate limit : max retries atteint")





def _build_prop_string(key: str, value) -> str:
    """Formate une prop pour le JSX : key={value} ou key="value"."""
    if isinstance(value, bool):
        return f"{key}={{{str(value).lower()}}}"
    elif isinstance(value, (int, float)):
        return f"{key}={{{value}}}"
    else:
        safe_value = str(value).replace('"', '\\"').replace("\n", " ")
        return f'{key}="{safe_value}"'


def _build_component_jsx(
    react_name: str,
    props_values: dict,
    child_interactions: dict | None = None,
    route_by_node_id: dict | None = None,
) -> str:
    """Construit l'appel JSX d'un composant avec ses props + interactions enfants."""
    # ✅ NOUVEAU : sanitizer le nom au cas où il contient des espaces
    react_name = _sanitize_component_name(react_name)
    
    parts = [_build_prop_string(k, v) for k, v in props_values.items()]
    
    # Ajouter les props onXxxClick depuis child_interactions
    if child_interactions and route_by_node_id is not None:
        for figma_name, interactions in child_interactions.items():
            handler = _build_onclick_handler(interactions, route_by_node_id)
            if handler:
                prop_name = _build_onclick_prop_name(figma_name)
                parts.append(f"{prop_name}={{{handler}}}")
    
    if not parts:
        return f"<{react_name} />"
    return f"<{react_name} {' '.join(parts)} />"


def _build_onclick_prop_name(figma_name: str) -> str:
    """Convertit 'Projects' → 'onProjectsClick', 'About me' → 'onAboutMeClick'."""
    safe = _sanitize_component_name(figma_name)
    return f"on{safe}Click"


def _build_onclick_handler(interactions: list, route_by_node_id: dict) -> str | None:
    """Construit le handler JS depuis une liste d'interactions.
    
    Retourne par exemple : "() => navigate('/projects')" ou "() => navigate(-1)"
    """
    if not isinstance(interactions, list):
        return None
    
    click_inter = next(
        (i for i in interactions if i.get("trigger") == "ON_CLICK"),
        None,
    )
    if not click_inter:
        return None
    
    actions = click_inter.get("actions", [])
    if not actions:
        return None
    
    first = actions[0]
    atype = first.get("type")
    nav = first.get("navigation")
    dest_id = first.get("destinationId")
    
    # NAVIGATE
    if nav == "NAVIGATE" and dest_id:
        route = route_by_node_id.get(dest_id)
        if route:
            return f"() => navigate('{route}')"
        return None
    
    # SCROLL_TO
    if nav == "SCROLL_TO" and dest_id:
        html_id = _html_id_from_figma_id(dest_id)
        return (
            f'() => document.getElementById("{html_id}")'
            f'?.scrollIntoView({{ behavior: "smooth" }})'
        )
    
    # OVERLAY
    if nav == "OVERLAY" and dest_id:
        return f'() => setActiveOverlay("{dest_id}")'
    
    # BACK
    if atype == "BACK":
        return "() => navigate(-1)"
    
    return None





def _sanitize_component_name(raw_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", raw_name).strip()
    parts = cleaned.split()
    proper = "".join(p[0].upper() + p[1:] if p else "" for p in parts)
    if proper and proper[0].isdigit():
        proper = "C" + proper
    return proper or "Component"



def _sanitize_prop_name(raw_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", raw_name).strip()
    parts = cleaned.split()

    if not parts:
        return "prop"

    first = parts[0].lower()
    rest = [p[0].upper() + p[1:] for p in parts[1:]]

    return first + "".join(rest)    

def _extract_component_usage(component: dict) -> dict:
    usage = {}

    imports_local = component.get("imports", {}).get("local", [])
    children_tree = component.get("architecture", {}).get("children_tree", {})

    # Permet de matcher les noms Figma et les noms React sanitizés
    imports_by_name = {}
    for imp in imports_local:
        name = imp.get("name", "")
        imports_by_name[name] = imp
        imports_by_name[_sanitize_component_name(name)] = imp

    parent_props = component.get("architecture", {}).get("props", [])
    parent_prop_names = [p.get("name") for p in parent_props]

    def walk(node):
        if not isinstance(node, dict):
            return

        if node.get("type") == "INSTANCE":
            instance_name = node.get("name", "")

            matched_import = imports_by_name.get(instance_name) or imports_by_name.get(
                _sanitize_component_name(instance_name)
            )

            if matched_import:
                react_component_name = _sanitize_component_name(instance_name)
                props_mapping = {}

                # Figma variant props -> React props
                for figma_prop, value in matched_import.get("props", {}).items():
                    react_prop = _sanitize_prop_name(figma_prop)

                    if isinstance(value, dict):
                        default_value = value.get("default")
                    else:
                        default_value = value

                    if default_value is not None:
                        props_mapping[react_prop] = default_value

                # Text children -> parent props
                for child in node.get("children", []):
                    if child.get("type") == "TEXT":
                        text_name = child.get("name", "")
                        react_prop = _sanitize_prop_name(text_name)

                        if react_prop in parent_prop_names:
                            props_mapping[react_prop] = f"{{{react_prop}}}"

                usage_key = f"{react_component_name}_{len(usage)}"
                usage[usage_key] = {
                    "react_component": react_component_name,
                    "figma_instance_name": instance_name,
                    "props_mapping": props_mapping,
                }
                return

        for child in node.get("children", []):
            walk(child)

    walk(children_tree)
    return usage


def _build_user_payload(component: dict, name_map: dict) -> str:
    safe_component = json.loads(json.dumps(component, ensure_ascii=False))

    raw_name = safe_component["name"]
    safe_component["name"] = name_map.get(raw_name, _sanitize_component_name(raw_name))
    safe_component["suggested_file"] = f"src/components/{safe_component['name']}.tsx"

    imports = safe_component.get("imports", {})
    for imp in imports.get("local", []):
        original = imp.get("name", "")
        imp["name"] = name_map.get(original, _sanitize_component_name(original))

    payload = {
      "name": safe_component["name"],
      "kind": safe_component["kind"],
      "suggested_file": safe_component["suggested_file"],
      "architecture": safe_component["architecture"],
      "styles": safe_component["styles"],
      "interactions": safe_component.get("interactions", {}),  # ← AJOUT
      "imports": safe_component.get("imports", {"local": [], "external": []}),
      "component_usage": _extract_component_usage(safe_component),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def _clean_llm_code(raw: str) -> str:
    raw = raw.strip()
    fence_pattern = r"^```(?:tsx|jsx|typescript|javascript|ts|js)?\s*\n(.*?)\n```$"
    match = re.match(fence_pattern, raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        return "\n".join(lines).strip()
    return raw    











def _sanitize_page_name(name: str) -> str:
    """Convertit un nom de page Figma en PascalCase valide."""
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    cleaned = "".join(p[0].upper() + p[1:] for p in parts if p)
    return cleaned or "Page"


# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION D'UN COMPOSANT RÉUTILISABLE (LLM #1 + LLM #2)
# ═══════════════════════════════════════════════════════════════

def _generate_component(arch_entry: dict, llm: ChatMistralAI, name_map: dict) -> str:
    payload_str = _build_user_payload(arch_entry, name_map)
    user_message = f"Voici les données EXACTES :\n\n{payload_str}"

    raw = _call_llm(llm, SYSTEM_PROMPT, user_message)
    code = _clean_llm_code(raw)

    if "export default" not in code:
        raise RuntimeError("Code généré sans 'export default'")

    return code


def _prepare_section_tree(section_data: dict, route_by_node_id: dict | None = None) -> dict:
    """Prépare l'arbre de la section :
    - Remplace les __COMPONENT_PLACEHOLDER__ par leur jsx_call
    - Garde les styles, id et interactions à chaque nœud
    """
    if not isinstance(section_data, dict):
        return section_data

    route_by_node_id = route_by_node_id or {}

    if section_data.get("type") == "__COMPONENT_PLACEHOLDER__":
        react_name = section_data.get("react_component_name", "Component")
        props_values = section_data.get("props_values", {})
        child_interactions = section_data.get("child_interactions", {})   # ✅ NOUVEAU

        result = {
            "type": "__COMPONENT_PLACEHOLDER__",
            "jsx_call": _build_component_jsx(
                react_name,
                props_values,
                child_interactions=child_interactions,
                route_by_node_id=route_by_node_id,
            ),
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
            _prepare_section_tree(child, route_by_node_id)   # ✅ propager
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
    """Génère le JSX d'une section libre de manière déterministe.
 
    ── FIX double-positionnement ──────────────────────────────────
    section_data["styles"]["_position"] (position de la section
    RACINE relative à la page) est déjà utilisé par _generate_page
    pour envelopper cette section dans un <div absolute top-[..] 
    left-[..]>. Si on laisse ce même _position dans les styles
    envoyés à style_converter.py, celui-ci l'applique UNE SECONDE
    FOIS automatiquement (_convert_positioning), ce qui double le
    décalage (contenu 2x trop loin, scroll qui déborde).
 
    On neutralise donc _position UNIQUEMENT sur le nœud racine
    (copie superficielle, on ne touche pas au dict original ni aux
    enfants) avant de générer le JSX interne. Le _position original
    reste intact dans `section_data`, donc _generate_page peut
    toujours le lire pour construire le wrapper englobant.
    ══════════════════════════════════════════════════════════════
    """
    from generator.style_converter import generate_section_jsx_deterministic
 
    section_name = section_data.get("name", "Section")
 
    # Copie superficielle de la racine : on ne modifie pas section_data original
    root_for_jsx = dict(section_data)
    if isinstance(root_for_jsx.get("styles"), dict):
        root_styles = dict(root_for_jsx["styles"])  # copie du sous-dict styles
        root_styles.pop("_position", None)           # retire SEULEMENT ici
        root_for_jsx["styles"] = root_styles
 
    section_tree = _prepare_section_tree(root_for_jsx, route_by_node_id)
 
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


def generate_components(architecture: dict, llm: ChatMistralAI) -> None:
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

    # Map des noms originaux Figma vers les noms React sanitizés
    # Nécessaire pour _build_user_payload qui remplace les noms dans imports.local
    name_map = {c["name"]: _sanitize_component_name(c["name"]) for c in components}

    generated = 0
    skipped = 0

    for name in ordered_names:
        
        comp = comp_by_name.get(name)
        if not comp:
            print(f"[generateur] WARN : '{name}' dans generation_order mais absent des components")
            continue

        print(f"\n[generateur] Composant : {name}")
        try:
            code = _generate_component(comp, llm, name_map)

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

def _fmt_num(value) -> str:
    """Formate un nombre : enlève .0 si entier (même logique que style_converter._fmt)."""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _extract_top_level_position(data: dict):
    """Récupère (top, left) depuis data['styles']['_position'], si présent.
    C'est la position de la section/instance top-level relative à la page,
    calculée par section_extractor.py (offset local, PAS de coordonnées Figma globales).
    """
    styles = data.get("styles", {})
    if isinstance(styles, dict):
        pos = styles.get("_position")
        if isinstance(pos, dict):
            top = pos.get("top")
            left = pos.get("left")
            if top is not None and left is not None:
                return top, left
    return None

def _wrap_with_interaction(jsx: str, interaction, route_by_node_id: dict) -> str:
    """Enveloppe le JSX selon le nouveau format d'interactions.
    
    Format attendu (liste) :
    [{"trigger": "ON_CLICK", "actions": [{"type": "...", "navigation": "...", "destinationId": "..."}]}]
    """
    if not interaction:
        return jsx
    
    if not isinstance(interaction, list):
        return jsx
    
    # Prendre la première interaction ON_CLICK
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
    
    # NAVIGATE → <Link>
    if navigation == "NAVIGATE" and dest_id:
        route = route_by_node_id.get(dest_id)
        if route:
            return f'<Link to="{route}">{jsx}</Link>'
        return jsx
    
    # SCROLL_TO → button avec scrollIntoView
    if navigation == "SCROLL_TO" and dest_id:
        html_id = _html_id_from_figma_id(dest_id)
        return (
            f'<button type="button" onClick={{() => '
            f'document.getElementById("{html_id}")?.scrollIntoView({{ behavior: "smooth" }})'
            f'}}>{jsx}</button>'
        )
    
    # OVERLAY → button avec setActiveOverlay
    if navigation == "OVERLAY" and dest_id:
        return (
            f'<button type="button" onClick={{() => '
            f'setActiveOverlay("{dest_id}")'
            f'}}>{jsx}</button>'
        )
    
    # BACK → navigate(-1)
    if action_type == "BACK":
        return (
            f'<button type="button" onClick={{() => navigate(-1)}}>{jsx}</button>'
        )
    
    return jsx




def _tree_has_interaction_type(node: dict, navigation_type: str) -> bool:
    """Vérifie si l'arbre contient une interaction du type donné.
    
    navigation_type : 'NAVIGATE', 'SCROLL_TO', 'OVERLAY' ou 'BACK'
    """
    if not isinstance(node, dict):
        return False
    
    interaction = node.get("interaction")
    if isinstance(interaction, list):
        for inter in interaction:
            for action in inter.get("actions", []):
                if navigation_type == "BACK":
                    if action.get("type") == "BACK":
                        return True
                else:
                    if action.get("navigation") == navigation_type:
                        return True
    
    for child in node.get("children", []):
        if _tree_has_interaction_type(child, navigation_type):
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

    for page in sections_data.get("pages", []):
        safe_name = _sanitize_page_name(page.get("page_name", "Page"))
        route = _route_from_page_name(safe_name)

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

def _generate_page(page: dict, llm = None) -> tuple[str, str, int, int]:
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
    needs_navigate_hook = False
    needs_overlay_state = False
 
    def _check_interaction(interaction):
        """Détecte les besoins depuis une interaction (liste, nouveau format)."""
        nonlocal needs_link, needs_navigate_hook, needs_overlay_state
 
        if not isinstance(interaction, list):
            return
 
        for inter in interaction:
            for action in inter.get("actions", []):
                nav = action.get("navigation")
                atype = action.get("type")
 
                if nav == "NAVIGATE":
                    needs_link = True
                    needs_navigate_hook = True   # besoin de navigate() pour child_interactions
                elif nav == "OVERLAY":
                    needs_overlay_state = True
                elif atype == "BACK":
                    needs_navigate_hook = True
 
    for child in ordered_children:
        data = child.get("data", {})
        _check_interaction(data.get("interaction"))
 
        # Détecter les besoins depuis child_interactions
        child_interactions = data.get("child_interactions", {})
        for inters in child_interactions.values():
            _check_interaction(inters)
 
        if child["kind"] == "instance":
            imports_needed.add(data.get("react_component_name"))
 
        elif child["kind"] == "section":
            if _tree_has_interaction_type(data, "NAVIGATE"):
                needs_link = True
            if _tree_has_interaction_type(data, "OVERLAY"):
                needs_overlay_state = True
            if _tree_has_interaction_type(data, "BACK"):
                needs_navigate_hook = True
 
            for inst in child.get("nested_instances", []):
                imports_needed.add(inst.get("react_component_name"))
                _check_interaction(inst.get("interaction"))
 
                inst_child_inter = inst.get("child_interactions", {})
                for inters in inst_child_inter.values():
                    _check_interaction(inters)
 
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
            child_interactions = data.get("child_interactions", {})
 
            jsx = _build_component_jsx(
                react_name,
                props_values,
                child_interactions=child_interactions,
                route_by_node_id=route_by_node_id,
            )
            jsx = _wrap_with_interaction(
                jsx,
                data.get("interaction"),
                route_by_node_id,
            )
 
            # wrapper avec id pour permettre le scroll
            instance_id = data.get("id")
            if instance_id:
                html_id = _html_id_from_figma_id(instance_id)
                jsx = f'<div id="{html_id}">{jsx}</div>'
 
            # ─── NOUVEAU : positionnement absolu top-level ───
            # Place l'instance à sa vraie position sur le canvas de la page
            # (relative à la page, calculée dans section_extractor.py).
            top_pos = _extract_top_level_position(data)
            if top_pos:
                top, left = top_pos
                jsx = (
                    f'<div className="absolute top-[{_fmt_num(top)}px] '
                    f'left-[{_fmt_num(left)}px]">{jsx}</div>'
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
 
                # ─── NOUVEAU : positionnement absolu top-level ───
                # Place la section à sa vraie position sur le canvas de la page
                # (relative à la page, calculée dans section_extractor.py).
                top_pos = _extract_top_level_position(data)
                if top_pos:
                    top, left = top_pos
                    jsx = (
                        f'<div className="absolute top-[{_fmt_num(top)}px] '
                        f'left-[{_fmt_num(left)}px]">\n{jsx}\n</div>'
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
 
    # Imports React Router (Link + useNavigate selon les besoins)
    router_imports = []
    if needs_link:
        router_imports.append("Link")
    if needs_navigate_hook:
        router_imports.append("useNavigate")
 
    if router_imports:
        import_lines.append(
            f"import {{ {', '.join(router_imports)} }} from 'react-router-dom';"
        )
 
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
    real_content_bottom = 0
    for _child in ordered_children:
        _child_data = _child.get("data", {})
        _child_styles = _child_data.get("styles", {})
        if not isinstance(_child_styles, dict):
            continue
        _pos = _child_styles.get("_position")
        _height = _child_styles.get("height")
        if isinstance(_pos, dict) and _height:
            _top = _pos.get("top", 0) or 0
            real_content_bottom = max(real_content_bottom, _top + _height)
        if real_content_bottom > 0:
            page_height = int(round(real_content_bottom))         



    # Construction des hooks (navigate + activeOverlay)
    hooks_lines = []
    if needs_navigate_hook:
        hooks_lines.append("  const navigate = useNavigate();")
    if needs_overlay_state or overlay_blocks:
        hooks_lines.append("  const [activeOverlay, setActiveOverlay] = useState<string | null>(null);")
 
    hooks_block = "\n".join(hooks_lines)
    if hooks_block:
        hooks_block += "\n"
 
    page_code = f"""import React, {{ useEffect, useState }} from 'react';{imports_str}
 
export default function {file_name}() {{
  const [scale, setScale] = useState(1);
{hooks_block}
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
      className="w-full overflow-hidden relative{page_bg}"
      style={{{{ height: `${{{page_height} * scale}}px` }}}}
    >
      <div
        className="absolute top-0 left-1/2"
        style={{{{
          width: `{page_width}px`,
          height: `{page_height}px`,
          transform: `translateX(-50%) scale(${{scale}})`,
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

def generate_pages(sections_data: dict, llm = None) -> None:
    """Génère tous les fichiers de pages."""
    print("\n[generateur] === Génération des pages ===")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    route_by_node_id = _build_route_by_node_id(sections_data)

    all_pages = []
    for page in sections_data.get("pages", []):
        safe_name = _sanitize_page_name(page.get("page_name", "Page"))
        route = _route_from_page_name(safe_name)

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

    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY manquant dans .env")

    llm = ChatMistralAI(
        model=CODESTRAL_MODEL,
        api_key=MISTRAL_API_KEY,
        temperature=0,
        max_tokens=4000,
    )

    all_component_names = [
        c.get("name") for c in architecture.get("components", [])
        if c.get("name")
    ]
    print(f"[generateur] {len(all_component_names)} composants trouvés dans architecture.json : {sorted(all_component_names)}")

    generate_components(architecture, llm)
    # ─── Étape 2 : pages ───
    generate_pages(sections_data, None)

    print("\n[generateur] === Génération terminée ===")
    print(f"[generateur] Projet → {PROJECT_DIR}")


def run_generateur_page(page_name: str) -> None:
    """Régénère une seule page par son nom (utile pour debug)."""
    print(f"\n[generateur] Régénération de la page '{page_name}'...")

    with open(SECTIONS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        sections_data = json.load(f)

    

    matching = [
        p for p in sections_data.get("pages", [])
        if p["page_name"] == page_name
    ]

    if not matching:
        print(f"[generateur] Page '{page_name}' non trouvée.")
        return

    route_by_node_id = _build_route_by_node_id(sections_data)

    all_pages = []
    for p in sections_data.get("pages", []):
        safe_name = _sanitize_page_name(p.get("page_name", "Page"))
        route = _route_from_page_name(safe_name)

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

        file_name, page_code, _, _ = _generate_page(page, None)

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