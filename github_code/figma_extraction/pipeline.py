import json
#from config.settings import CLEANED_OUTPUT_FILE
from config.settings import MINIMAL_OUTPUT_FILE
from .fetcher import fetch_and_save
from .canvas_filter import filter_canvases
from .cleaner import clean_tree


def save_cleaned(data: dict) -> None:
    """
    Sauvegarde le JSON nettoyé.
    """
    MINIMAL_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(MINIMAL_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = MINIMAL_OUTPUT_FILE.stat().st_size / 1024
    print(f"[pipeline] JSON nettoyé sauvegardé -> {MINIMAL_OUTPUT_FILE} ({size_kb:.1f} KB)")


def run_figma_extraction_pipeline() -> dict:
    """
    Pipeline complet :
    1. Fetch JSON Figma
    2. Filter canvases
    3. Clean nodes
    4. Save résultat
    """
    print("\n=== Figma Extraction Pipeline ===")

    raw_data = fetch_and_save()
    filtered_data = filter_canvases(raw_data)
    cleaned_data = clean_tree(filtered_data)

    save_cleaned(cleaned_data)

    print("[pipeline] Extraction terminée avec succès.")
    return cleaned_data