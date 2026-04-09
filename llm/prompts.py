"""
prompts.py
----------
Tous les prompts centralisés avec ChatPromptTemplate de LangChain.
Chaque fonction retourne un ChatPromptTemplate prêt à être chaîné avec le LLM.
"""

import json
from typing import Any
from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# System message commun
# ---------------------------------------------------------------------------

SYSTEM_MESSAGE = (
    "Tu es un expert en architecture frontend React moderne. "
    "Tu réponds TOUJOURS en JSON valide, sans markdown, sans backticks, "
    "sans commentaires. Uniquement du JSON pur."
)

# ---------------------------------------------------------------------------
# Modèle de structure de fichier commun à tous les prompts
# ---------------------------------------------------------------------------

FILE_STRUCTURE_EXAMPLE = """{{
    "path": "src/components/Header.jsx",
    "type": "component",
    "component_name": "Header",
    "figma_node_id": "15:42",
    "depends_on": [],
    "reuses_figma_component": "2:1015",
    "description": "...",
}}"""

# ---------------------------------------------------------------------------
# Prompt : appel unique
# ---------------------------------------------------------------------------

_SINGLE_CALL_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_MESSAGE),
    ("human", """
Tu reçois un payload extrait d'un design Figma contenant :
- `figma_tree` : l'arbre structurel du design (frames, instances, composants)
- `reusable_components` : les composants Figma réutilisables 

Ton objectif : analyser ce design et produire un planning complet de génération de code React.

RÈGLES STRICTES :
1. IDS FIGMA :
   - Pour les sections et pages : trouve leur `id` dans `figma_tree` → `figma_node_id`
   - Pour les composants réutilisables : utilise leur `component_id` ou `component_set_id` 
     depuis `reusable_components` → `figma_node_id`
   - Si le nom d'un variant_set décrit une PROPRIÉTÉ et non un composant UI 
     (ex: "Size", "Active", "Color"), déduis le vrai nom du composant React 
     depuis son contexte (used_in_frames, variants).
2. Chaque composant Figma réutilisable → 1 composant React séparé.
3. Chaque FRAME de niveau 1 dans figma_tree → une section ou page React.
4. Ordre de génération : du plus indépendant au plus dépendant.
   (les composants atomiques avant les sections, les sections avant les pages)

PAYLOAD FIGMA :
{payload}

Retourne UNIQUEMENT ce JSON :
{{
  "project_name": "...",
  "description": "...",
  "folders": [{{"path": "src/components", "purpose": "..."}}],
  "files": [""" + FILE_STRUCTURE_EXAMPLE + """],
  "routes": [{{"path": "/", "page_component": "HomePage", "file_path": "src/pages/HomePage.jsx"}}],
  "dependencies": [{{"package": "react-router-dom", "reason": "..."}}],
  "generation_order": ["src/components/Header.jsx"],
  "notes": "..."
}}
"""),
])


def build_single_call_prompt(payload: dict[str, Any]) -> ChatPromptTemplate:
    return _SINGLE_CALL_TEMPLATE.partial(
        payload=json.dumps(payload, ensure_ascii=False, indent=2)
    )


# ---------------------------------------------------------------------------
# Prompt : premier chunk
# ---------------------------------------------------------------------------

_FIRST_CHUNK_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_MESSAGE),
    ("human", """
Tu analyses un design Figma par morceaux. C'est le PREMIER morceau.

RÉSUMÉ GLOBAL DU DESIGN :
{global_summary}

COMPOSANTS FIGMA RÉUTILISABLES (définitions complètes avec vraies props) :
{reusable_components}

MORCEAU À ANALYSER :
{chunk}

Identifie les composants React et fichiers pour CE morceau uniquement.

RÈGLES STRICTES :
1. IDS FIGMA :
   - Pour les sections et pages : trouve leur `id` dans le morceau → `figma_node_id`
   - Pour les composants réutilisables : utilise leur `component_id` ou `component_set_id`
     depuis `reusable_components` → `figma_node_id`
   - Si le nom d'un variant_set décrit une PROPRIÉTÉ et non un composant UI
     (ex: "Size", "Active", "Color"), déduis le vrai nom du composant React
     depuis son contexte (used_in_frames, variants).
2. Chaque composant Figma réutilisable → 1 composant React séparé.
3. Chaque FRAME de niveau 1 dans le morceau → une section ou page React.
4. DEPENDS_ON : Remplis `depends_on` ainsi :
   - Pour un COMPOSANT réutilisable : consulte `component_dependencies` 
     dans le payload. Si le composant y apparaît comme clé, liste ses valeurs.
     Exemple : "Header": ["Tab", "Active"] → Header.depends_on: ["Tab", "Active"]
   - Pour une SECTION : liste les `component_name` des composants dont
     les `used_in_frames` contiennent l'id de cette section.
   - Pour une PAGE : liste toutes les sections et composants directs.
5. Ordre de génération : du plus indépendant au plus dépendant.
   (composants atomiques → composants complexes → sections → pages)
Retourne UNIQUEMENT ce JSON :
{{
  "project_name": "...",
  "description": "...",
  "folders": [{{"path": "...", "purpose": "..."}}],
  "files": [""" + FILE_STRUCTURE_EXAMPLE + """],
  "routes": [],
  "dependencies": [],
  "generation_order": [],
  "notes": "..."
}}
"""),
])


def build_first_chunk_prompt(
    chunk: dict[str, Any],
    reusable_components: list[dict[str, Any]],
    global_summary: dict[str, Any],
) -> ChatPromptTemplate:
    return _FIRST_CHUNK_TEMPLATE.partial(
        chunk=json.dumps(chunk, ensure_ascii=False, indent=2),
        reusable_components=json.dumps(reusable_components, ensure_ascii=False, indent=2),
        global_summary=json.dumps(global_summary, ensure_ascii=False, indent=2),
    )


# ---------------------------------------------------------------------------
# Prompt : chunks suivants (rolling context)
# ---------------------------------------------------------------------------

_NEXT_CHUNK_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_MESSAGE),
    ("human", """
Tu analyses un design Figma par morceaux. Morceau {chunk_index}/{total_chunks}.

CE QUI A DÉJÀ ÉTÉ IDENTIFIÉ :
{cumulative_summary}

COMPOSANTS FIGMA RÉUTILISABLES :
{reusable_components}

NOUVEAU MORCEAU À ANALYSER :
{chunk}

Identifie UNIQUEMENT les nouveaux éléments (IDs depuis le morceau ou reusable_components, pas de layout, pas de props).

Retourne UNIQUEMENT ce JSON :
{{
  "project_name": "...",
  "description": "...",
  "folders": [],
  "files": [""" + FILE_STRUCTURE_EXAMPLE + """],
  "routes": [],
  "dependencies": [],
  "generation_order": [],
  "notes": "nouvelles observations"
}}
"""),
])


def build_next_chunk_prompt(
    chunk: dict[str, Any],
    cumulative_summary: dict[str, Any],
    reusable_components: list[dict[str, Any]],
    chunk_index: int,
    total_chunks: int,
) -> ChatPromptTemplate:
    return _NEXT_CHUNK_TEMPLATE.partial(
        chunk=json.dumps(chunk, ensure_ascii=False, indent=2),
        cumulative_summary=json.dumps(cumulative_summary, ensure_ascii=False, indent=2),
        reusable_components=json.dumps(reusable_components, ensure_ascii=False, indent=2),
        chunk_index=str(chunk_index),
        total_chunks=str(total_chunks),
    )


# ---------------------------------------------------------------------------
# Prompt : fusion des plannings partiels
# ---------------------------------------------------------------------------

_MERGE_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_MESSAGE),
    ("human", """
Tu reçois des plannings partiels issus de différents morceaux d'un même design Figma.
Fusionne-les en UN SEUL planning final cohérent.

RÈGLES DE FUSION :
1. Déduplique composants, dossiers et dépendances en gardant les `figma_node_id` et `layout_strategy`.
2. Fusionne les props (liste de dictionnaires) si un composant apparaît plusieurs fois.
3. Construis un ordre de génération global cohérent.

PLANNINGS PARTIELS :
{partial_plannings}

Retourne UNIQUEMENT ce JSON :
{{
  "project_name": "...",
  "description": "...",
  "folders": [{{"path": "...", "purpose": "..."}}],
  "files": [""" + FILE_STRUCTURE_EXAMPLE + """],
  "routes": [{{"path": "/", "page_component": "...", "file_path": "..."}}],
  "dependencies": [{{"package": "...", "reason": "..."}}],
  "generation_order": [],
  "notes": "..."
}}
"""),
])


def build_merge_prompt(partial_plannings: list[dict[str, Any]]) -> ChatPromptTemplate:
    return _MERGE_TEMPLATE.partial(
        partial_plannings=json.dumps(partial_plannings, ensure_ascii=False, indent=2)
    )


# ---------------------------------------------------------------------------
# Prompt : résumé cumulatif (rolling context)
# ---------------------------------------------------------------------------

_SUMMARY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_MESSAGE),
    ("human", """
Résume ce planning partiel de manière très compacte.
Garde uniquement l'essentiel pour contextualiser le prochain morceau.

PLANNING PARTIEL :
{partial_planning}

Retourne UNIQUEMENT ce JSON :
{{
  "components_identified": ["Header", "Footer", "ProductCard"],
  "pages_identified": ["HomePage"],
  "folders_identified": ["src/components", "src/pages"],
  "key_observations": ["utilise un système de tabs", "cards réutilisables"]
}}
"""),
])


def build_summary_prompt(partial_planning: dict[str, Any]) -> ChatPromptTemplate:
    return _SUMMARY_TEMPLATE.partial(
        partial_planning=json.dumps(partial_planning, ensure_ascii=False, indent=2)
    )