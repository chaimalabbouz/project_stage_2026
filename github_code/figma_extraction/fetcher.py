import json
import time
from pathlib import Path

import requests

from config.settings import FIGMA_API_KEY, FIGMA_FILE_KEY, RAW_OUTPUT_FILE

FIGMA_API_BASE = "https://api.figma.com/v1"


def fetch_figma_file(file_id: str = FIGMA_FILE_KEY) -> dict:
    """
    Appelle l'API Figma et retourne le JSON brut du fichier.
    Réessaie automatiquement si Figma répond 429.
    """
    url = f"{FIGMA_API_BASE}/files/{file_id}"
    headers = {"X-Figma-Token": FIGMA_API_KEY}

    print(f"[fetcher] Récupération du fichier Figma : {file_id}")

    max_retries = 5

    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            print("[fetcher] Fichier récupéré avec succès.")
            return data

        if response.status_code == 429:
            wait_time = 2 ** attempt
            print(f"[fetcher] Rate limit atteint. Attente de {wait_time}s avant retry...")
            time.sleep(wait_time)
            continue

        raise RuntimeError(f"Erreur API Figma {response.status_code} : {response.text}")

    raise RuntimeError("Erreur API Figma 429 : trop de tentatives, réessaie plus tard.")


def save_raw(data: dict, path: Path = RAW_OUTPUT_FILE) -> None:
    """
    Sauvegarde le JSON brut sur disque.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = path.stat().st_size / 1024
    print(f"[fetcher] Raw sauvegardé -> {path} ({size_kb:.1f} KB)")


def fetch_and_save(file_id: str = FIGMA_FILE_KEY) -> dict:
    """
    Point d'entrée principal : fetch + save raw + retourne le dict.
    """
    data = fetch_figma_file(file_id)
    save_raw(data)
    return data