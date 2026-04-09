"""
client.py
---------
Point d'entrée unique vers l'API Groq.
Toute la configuration du modèle est centralisée ici.
"""

import os
import json
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Modèles disponibles (100% gratuits sur Groq)
MODELS = {
    "default": "moonshotai/kimi-k2-instruct",       # modèle principal demandé
    "large": "llama-3.3-70b-versatile",              # modèle de fallback (contexte large, gratuit)
}

# Limites de contexte approximatives en tokens
MODEL_CONTEXT_LIMITS = {
    "moonshotai/kimi-k2-instruct": 128_000,
    "llama-3.3-70b-versatile": 128_000,
}

# Marge de sécurité : on utilise max 70% du contexte pour laisser de la place à la réponse
CONTEXT_SAFETY_RATIO = 0.70


def get_context_limit(model: str) -> int:
    """Retourne la limite de tokens utilisable pour un modèle donné."""
    limit = MODEL_CONTEXT_LIMITS.get(model, 32_000)
    return int(limit * CONTEXT_SAFETY_RATIO)


def call_llm(
    prompt: str,
    model: str = MODELS["default"],
    max_tokens: int = 4096,
    temperature: float = 0.2,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> str:
    """
    Appel unique au LLM Groq.

    Args:
        prompt: Le prompt complet à envoyer.
        model: Identifiant du modèle Groq à utiliser.
        max_tokens: Nombre max de tokens dans la réponse.
        temperature: Créativité du modèle (0.2 = déterministe).
        retries: Nombre de tentatives en cas d'erreur.
        retry_delay: Délai entre les tentatives (secondes).

    Returns:
        Le texte brut retourné par le LLM.

    Raises:
        RuntimeError: Si toutes les tentatives échouent.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY manquant dans le fichier .env")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es un expert en architecture frontend React. "
                    "Tu réponds TOUJOURS en JSON valide, sans markdown, "
                    "sans backticks, sans commentaires. "
                    "Uniquement du JSON pur."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                GROQ_API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            print(f"[client] Tentative {attempt}/{retries} échouée (HTTP {status}): {e}")
            last_error = e

            # Rate limit → attendre plus longtemps
            if status == 429:
                time.sleep(retry_delay * attempt * 2)
            else:
                time.sleep(retry_delay * attempt)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"[client] Tentative {attempt}/{retries} échouée (réseau): {e}")
            last_error = e
            time.sleep(retry_delay * attempt)

        except (KeyError, json.JSONDecodeError) as e:
            print(f"[client] Tentative {attempt}/{retries} échouée (parsing): {e}")
            last_error = e
            time.sleep(retry_delay)

    raise RuntimeError(
        f"[client] Toutes les tentatives ont échoué. Dernière erreur: {last_error}"
    )


def call_llm_with_fallback(
    prompt: str,
    preferred_model: str = MODELS["default"],
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> tuple[str, str]:
    """
    Essaie d'abord le modèle préféré, puis bascule sur le modèle large si échec.

    Returns:
        Tuple (réponse_texte, modèle_utilisé)
    """
    try:
        result = call_llm(prompt, model=preferred_model, max_tokens=max_tokens, temperature=temperature)
        return result, preferred_model
    except RuntimeError as e:
        print(f"[client] Fallback vers modèle large. Raison: {e}")
        fallback = MODELS["large"]
        result = call_llm(prompt, model=fallback, max_tokens=max_tokens, temperature=temperature)
        return result, fallback