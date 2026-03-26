import json
from pathlib import Path

import requests

from config.settings import FIGMA_API_KEY, FIGMA_FILE_ID, RAW_OUTPUT_FILE

FIGMA_API_BASE = "https://api.figma.com/v1"


def fetch_figma_file(file_id: str = FIGMA_FILE_ID) -> dict:
    """
    Appelle l'API Figma et retourne le JSON brut du fichier.
    Lève une exception si la requête échoue.
    """
    url = f"{FIGMA_API_BASE}/files/{file_id}"
    headers = {"X-Figma-Token": FIGMA_API_KEY}

    print(f"[fetcher] Récupération du fichier Figma : {file_id}")
    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Erreur API Figma {response.status_code} : {response.text}")

    data = response.json()
    print("[fetcher] Fichier récupéré avec succès.")
    return data


def save_raw(data: dict, path: Path = RAW_OUTPUT_FILE) -> None:
    """
    Sauvegarde le JSON brut sur disque.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = path.stat().st_size / 1024
    print(f"[fetcher] Raw sauvegardé -> {path} ({size_kb:.1f} KB)")


def fetch_and_save(file_id: str = FIGMA_FILE_ID) -> dict:
    """
    Point d'entrée principal : fetch + save raw + retourne le dict.
    """
    data = fetch_figma_file(file_id)
    save_raw(data)
    return data