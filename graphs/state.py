"""
state.py
--------
État global du graph LangGraph.
Contient tous les champs produits et consommés par les noeuds du graph.
"""

from typing import Any, Literal
from typing_extensions import TypedDict


class PlannerGraphState(TypedDict, total=False):

    # -----------------------------------------------------------------------
    # Phase 1 : récupération et nettoyage Figma
    # -----------------------------------------------------------------------
    raw_json: dict[str, Any]
    filtered_json: dict[str, Any]
    cleaned_json: dict[str, Any]
    reusable_components: dict[str, Any]

    # -----------------------------------------------------------------------
    # Phase 2 : construction du payload
    # -----------------------------------------------------------------------
    planner_input: dict[str, Any]
    planner_feasibility: Literal["ready", "large_model_required"]

    # -----------------------------------------------------------------------
    # Phase 3 : génération LLM
    # -----------------------------------------------------------------------
    llm_planning: dict[str, Any]        # planning final complet validé par Pydantic
    llm_model_used: str                 # modèle Groq effectivement utilisé

    # -----------------------------------------------------------------------
    # Logs
    # -----------------------------------------------------------------------
    logs: list[str]


    # -----------------------------------------------------------------------
    # Phase 4 : Génération de code
    # -----------------------------------------------------------------------
    generated_project_path: str         # Chemin du projet React généré (ex: data/mon_projet)