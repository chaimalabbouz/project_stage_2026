"""
client.py
---------
Client LLM utilisant LangChain + ChatGroq.
Point d'entrée unique vers Groq, toute la config est centralisée ici.
"""

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# Modèles disponibles (100% gratuits sur Groq)
MODELS = {
    "default": "moonshotai/kimi-k2-instruct",
    "large": "llama-3.3-70b-versatile",
}

# Limites de contexte utilisables (70% de la limite réelle)
MODEL_CONTEXT_LIMITS = {
    "moonshotai/kimi-k2-instruct": int(128_000 * 0.70),
    "llama-3.3-70b-versatile": int(128_000 * 0.70),
}


def get_llm(model: str = MODELS["default"], temperature: float = 0.2) -> ChatGroq:
    """
    Retourne une instance ChatGroq configurée.

    Args:
        model: Identifiant du modèle Groq.
        temperature: Créativité du modèle (0.2 = déterministe).

    Returns:
        Instance ChatGroq prête à l'emploi.
    """
    return ChatGroq(
        model=model,
        temperature=temperature,
        max_retries=3,
        api_key=os.getenv("GROQ_API_KEY", ""),
    )


def get_context_limit(model: str) -> int:
    """Retourne la limite de tokens utilisable pour un modèle donné."""
    return MODEL_CONTEXT_LIMITS.get(model, int(32_000 * 0.70))