import json
import os
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

from config.settings import ARCHITECTURE_FILE, SECTIONS_OUTPUT_FILE


from config.settings  import ASSETS_DIR
IMAGE_REF_RE = re.compile(r"^[a-f0-9]{32,64}$", re.IGNORECASE)


def _is_image_ref(value) -> bool:
    return isinstance(value, str) and bool(IMAGE_REF_RE.match(value))


def _collect_image_refs_from_obj(obj, refs: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "imageRef" and isinstance(value, str):
                refs.add(value)
            elif _is_image_ref(value):
                refs.add(value)
            else:
                _collect_image_refs_from_obj(value, refs)

    elif isinstance(obj, list):
        for item in obj:
            _collect_image_refs_from_obj(item, refs)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _replace_image_refs_in_obj(obj, ref_to_local: dict[str, str]):
    if isinstance(obj, dict):
        for key, value in list(obj.items()):
            if isinstance(value, str) and value in ref_to_local:
                obj[key] = ref_to_local[value]
            else:
                _replace_image_refs_in_obj(value, ref_to_local)

    elif isinstance(obj, list):
        for item in obj:
            _replace_image_refs_in_obj(item, ref_to_local)


def _get_figma_image_urls(figma_file_id: str, figma_api_key: str) -> dict[str, str]:
    url = f"https://api.figma.com/v1/files/{figma_file_id}/images"

    response = requests.get(
        url,
        headers={"X-Figma-Token": figma_api_key},
        timeout=60,
    )

    response.raise_for_status()
    data = response.json()

    return data.get("meta", {}).get("images", {})


def _download_file(url: str, output_path: Path) -> bool:
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(response.content)  

        return True

    except Exception as e:
        print(f"  [WARN] téléchargement échoué : {url} -> {e}")
        return False


def download_figma_images_and_rewrite_jsons() -> dict[str, str]:
    load_dotenv()

    figma_api_key = os.getenv("FIGMA_API_KEY")
    figma_file_id = os.getenv("FIGMA_FILE_ID")

    if not figma_api_key:
        raise RuntimeError("FIGMA_API_KEY manquant dans .env")

    if not figma_file_id:
        raise RuntimeError("FIGMA_FILE_ID manquant dans .env")

    architecture_data = _load_json(ARCHITECTURE_FILE)
    sections_data = _load_json(SECTIONS_OUTPUT_FILE)

    image_refs: set[str] = set()

    _collect_image_refs_from_obj(architecture_data, image_refs)
    _collect_image_refs_from_obj(sections_data, image_refs)

    if not image_refs:
        print("[image_downloader] Aucun imageRef trouvé.")
        return {}

    print(f"[image_downloader] {len(image_refs)} imageRef trouvés.")

    figma_images = _get_figma_image_urls(figma_file_id, figma_api_key)
    print(f"Total imageRef JSON: {len(image_refs)}")
    print(f"Images dispo Figma: {len(figma_images)}")
    ref_to_local: dict[str, str] = {}

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for image_ref in sorted(image_refs):
        image_url = figma_images.get(image_ref)

        if not image_url:
            print(f"  [WARN] imageRef absent de Figma images API : {image_ref}")
            continue

        filename = f"{image_ref}.png"
        output_path = ASSETS_DIR / filename
        public_path = f"/src/assets/{filename}"

        if output_path.exists():
            print(f"  [SKIP] existe déjà : {output_path}")
            ref_to_local[image_ref] = public_path
            continue

        ok = _download_file(image_url, output_path)

        if ok:
            print(f"  [OK] {image_ref} -> {output_path}")
            ref_to_local[image_ref] = public_path

    if ref_to_local:
        _replace_image_refs_in_obj(architecture_data, ref_to_local)
        _replace_image_refs_in_obj(sections_data, ref_to_local)

        _save_json(ARCHITECTURE_FILE, architecture_data)
        _save_json(SECTIONS_OUTPUT_FILE, sections_data)

        print(f"[image_downloader] JSON mis à jour avec {len(ref_to_local)} images.")

    return ref_to_local


if __name__ == "__main__":
    download_figma_images_and_rewrite_jsons()