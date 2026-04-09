import json
from typing import Any
from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Prompts système
# ---------------------------------------------------------------------------

_SYSTEM_COMPONENT = (
    "Tu es un développeur React expert. "
    "Tu génères UNIQUEMENT du code JSX valide, sans explications, "
    "sans markdown, sans backticks, sans commentaires superflus."
)

_SYSTEM_SECTION = (
    "Tu es un développeur React expert. "
    "Tu génères UNIQUEMENT le JSX d'une section — pas d'imports, pas d'export. "
    "Juste le bloc JSX entre parenthèses : ( <div>...</div> ). "
    "Sans markdown, sans backticks, sans explications."
)

_SYSTEM_ASSEMBLY = (
    "Tu es un développeur React expert. "
    "Tu assembles des sections JSX en un composant page React complet. "
    "Tu génères UNIQUEMENT du code JSX valide avec imports et export default. "
    "Sans markdown, sans backticks, sans explications."
)

# ---------------------------------------------------------------------------
# Template : génération d'un composant réutilisable
# ---------------------------------------------------------------------------

_COMPONENT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_COMPONENT),
    ("human", """
Génère le code React pour le composant décrit ci-dessous.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MÉTADONNÉES DU COMPOSANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Nom          : {component_name}
- Type         : {component_type}
- Description  : {description}
- Layout racine: {layout_strategy}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPOSANTS DÉJÀ GÉNÉRÉS (imports disponibles)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{existing_components}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARBORESCENCE FIGMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{figma_json}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Commence par les imports, termine par `export default {component_name}`.
2. Utilise UNIQUEMENT Tailwind CSS.
3. layoutMode HORIZONTAL → flex flex-row | VERTICAL → flex flex-col.
4. paddingLeft/Right/Top/Bottom → classes Tailwind (16px → px-4, 8px → py-2...).
5. itemSpacing → gap-X Tailwind.
6. fills color → classe bg- Tailwind la plus proche.
7. cornerRadius → rounded-md (4-8px) / rounded-lg (12-16px) / rounded-full (>50%).
8. characters → texte JSX tel quel.
9. Nœud INSTANCE → importe et utilise le composant correspondant, ne recrée jamais son code.
10. VECTOR, BOOLEAN_OPERATION → <div /> vide.
11. Image (fill type IMAGE) → <img src="" alt="nom du nœud" className="w-full h-auto object-cover" />.
12. Composant purement présentationnel → pas de state inutile.

Retourne UNIQUEMENT le code JSX brut.
"""),
])

# ---------------------------------------------------------------------------
# Template : génération du JSX d'une section (sans imports ni export)
# ---------------------------------------------------------------------------

_SECTION_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_SECTION),
    ("human", """
Génère le JSX de la section décrite ci-dessous.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOM DE LA SECTION : {section_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPOSANTS DISPONIBLES (balises JSX utilisables directement) :
{existing_components}

ARBORESCENCE FIGMA DE LA SECTION :
{figma_json}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Retourne UNIQUEMENT le JSX — pas d'imports, pas d'export, pas de fonction.
2. Format attendu : ( <div className="...">...</div> )
3. Utilise Tailwind CSS uniquement.
4. layoutMode HORIZONTAL → flex flex-row | VERTICAL → flex flex-col.
5. Si tu vois un nœud INSTANCE dont le nom correspond à un composant disponible → utilise sa balise JSX.
6. characters → texte JSX tel quel.
7. VECTOR → <div /> vide.
8. Image (fill IMAGE) → <img src="" alt="..." className="w-full h-auto object-cover" />.

Retourne UNIQUEMENT le bloc JSX brut entre parenthèses.
"""),
])

# ---------------------------------------------------------------------------
# Template : assemblage de la page depuis les sections JSX
# ---------------------------------------------------------------------------

_ASSEMBLY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_ASSEMBLY),
    ("human", """
Assemble la page React complète à partir des sections JSX fournies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOM DU COMPOSANT PAGE : {component_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPOSANTS DISPONIBLES ET LEURS CHEMINS D'IMPORT :
{existing_components}

SECTIONS JSX (dans l'ordre d'affichage) :
{sections_jsx}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES STRICTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Commence par les imports React et des composants utilisés.
2. Crée une fonction : export default function {component_name}() {{ ... }}
3. Le return contient TOUTES les sections dans l'ordre fourni, enveloppées dans un <div> racine.
4. N'invente PAS de nouvelles sections — utilise exactement ce qui est fourni.
5. Si une section utilise une balise JSX d'un composant disponible, importe-le avec son chemin exact.
6. Chaque balise JSX doit être correctement fermée.
7. Code complet jusqu'au dernier }} — ne jamais tronquer.

Retourne UNIQUEMENT le code JSX brut complet.
"""),
])


# ---------------------------------------------------------------------------
# Fonctions publiques
# ---------------------------------------------------------------------------

def get_component_prompt(
    component_info: dict[str, Any],
    figma_json: dict[str, Any],
    existing_components: dict[str, str],
) -> ChatPromptTemplate:
    """Prompt pour générer un composant réutilisable."""
    figma_str = json.dumps(figma_json, ensure_ascii=False, separators=(",", ":"))
    existing_str = json.dumps(existing_components, ensure_ascii=False, indent=2)

    return _COMPONENT_TEMPLATE.partial(
        component_name=component_info.get("component_name", "UnknownComponent"),
        component_type=component_info.get("type", "component"),
        description=component_info.get("description", ""),
        layout_strategy=component_info.get("layout_strategy", "flex flex-col"),
        existing_components=existing_str,
        figma_json=figma_str,
    )


def get_section_prompt(
    section_name: str,
    figma_json: dict[str, Any],
    existing_components: dict[str, str],
) -> ChatPromptTemplate:
    """Prompt pour générer le JSX d'une section (sans imports ni export)."""
    figma_str = json.dumps(figma_json, ensure_ascii=False, separators=(",", ":"))
    existing_str = json.dumps(existing_components, ensure_ascii=False, indent=2)

    return _SECTION_TEMPLATE.partial(
        section_name=section_name,
        existing_components=existing_str,
        figma_json=figma_str,
    )


def get_assembly_prompt(
    component_name: str,
    sections_jsx: list[dict[str, str]],
    existing_components: dict[str, str],
) -> ChatPromptTemplate:
    """Prompt pour assembler une page depuis ses sections JSX."""
    # Format lisible pour le LLM
    sections_str = "\n\n".join(
        f"--- Section '{s['name']}' ---\n{s['jsx']}"
        for s in sections_jsx
    )
    existing_str = json.dumps(existing_components, ensure_ascii=False, indent=2)

    return _ASSEMBLY_TEMPLATE.partial(
        component_name=component_name,
        existing_components=existing_str,
        sections_jsx=sections_str,
    )


# ---------------------------------------------------------------------------
# Rétrocompatibilité : ancien nom utilisé dans certains imports
# ---------------------------------------------------------------------------

def get_code_generation_prompt(
    component_info: dict[str, Any],
    figma_json: dict[str, Any],
    existing_components: dict[str, str],
) -> ChatPromptTemplate:
    """Alias vers get_component_prompt pour compatibilité."""
    return get_component_prompt(component_info, figma_json, existing_components)