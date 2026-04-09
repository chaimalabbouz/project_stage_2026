import json
import re
from typing import Any

from llm.client import get_llm, MODELS
from llm.prompts import (
    build_single_call_prompt,
    build_first_chunk_prompt,
    build_next_chunk_prompt,
    build_merge_prompt,
    build_summary_prompt,
)


def _make_chain(prompt_template, model: str):
    """
    Crée une chaîne LLM avec fallback vers le modèle large.
    Sans Pydantic parser: on récupère du JSON brut.
    """
    llm = get_llm(model=model)
    llm_large = get_llm(model=MODELS["large"])
    llm_with_fallback = llm.with_fallbacks([llm_large])
    return prompt_template | llm_with_fallback


def _strip_code_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def _extract_first_json_block(text: str) -> str:
    """
    Essaie d'extraire le premier bloc JSON si le modèle ajoute du texte autour.
    """
    text = _strip_code_fences(text)

    if text.startswith("{") and text.endswith("}"):
        return text
    if text.startswith("[") and text.endswith("]"):
        return text

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)

    raise ValueError("Aucun JSON valide trouvé dans la réponse du LLM.")


def _extract_json_from_response(response: Any) -> dict[str, Any]:
    """
    Convertit la réponse du LLM en dict Python.
    """
    content = response.content if hasattr(response, "content") else str(response)
    json_text = _extract_first_json_block(content)
    data = json.loads(json_text)

    if not isinstance(data, dict):
        raise ValueError("Le JSON retourné par le LLM doit être un objet JSON.")

    return data


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_planning(data: dict[str, Any]) -> dict[str, Any]:
    """
    Rend le planning plus robuste sans imposer un schéma strict.
    Mis à jour pour gérer figma_node_id, layout_strategy et les props structurées.
    """
    data = _safe_dict(data)

    normalized = {
        "project_name": data.get("project_name", ""),
        "description": data.get("description", ""),
        "folders": _safe_list(data.get("folders")),
        "files": _safe_list(data.get("files")),
        "routes": _safe_list(data.get("routes")),
        "dependencies": _safe_list(data.get("dependencies")),
        "generation_order": _safe_list(data.get("generation_order")),
        "notes": data.get("notes", ""),
    }

    clean_folders = []
    for folder in normalized["folders"]:
        if not isinstance(folder, dict):
            continue
        clean_folders.append(
            {
                "path": folder.get("path", ""),
                "purpose": folder.get("purpose", ""),
                **{k: v for k, v in folder.items() if k not in {"path", "purpose"}},
            }
        )
    normalized["folders"] = clean_folders

    clean_files = []
    for file in normalized["files"]:
        if not isinstance(file, dict):
            continue
        
        # Normalisation spécifique pour s'assurer que les nouveaux champs existent toujours
        clean_files.append(
            {
                "path": file.get("path", ""),
                "type": file.get("type", "component"),
                "component_name": file.get("component_name", ""),
                "figma_node_id": file.get("figma_node_id", ""),         # NOUVEAU
                "depends_on": _safe_list(file.get("depends_on")),
                "reuses_figma_component": file.get("reuses_figma_component"),
                "description": file.get("description", ""),
                **{
                    k: v
                    for k, v in file.items()
                    if k
                    not in {
                        "path", "type", "component_name", "figma_node_id",
                        "depends_on", "reuses_figma_component", "description",
                    }
                },
            }
        )
    normalized["files"] = clean_files

    clean_routes = []
    for route in normalized["routes"]:
        if not isinstance(route, dict):
            continue
        clean_routes.append(
            {
                "path": route.get("path", ""),
                "page_component": route.get("page_component", ""),
                "file_path": route.get("file_path", ""),
                **{
                    k: v
                    for k, v in route.items()
                    if k not in {"path", "page_component", "file_path"}
                },
            }
        )
    normalized["routes"] = clean_routes

    clean_dependencies = []
    for dep in normalized["dependencies"]:
        if not isinstance(dep, dict):
            continue
        clean_dependencies.append(
            {
                "package": dep.get("package", ""),
                "reason": dep.get("reason", ""),
                **{k: v for k, v in dep.items() if k not in {"package", "reason"}},
            }
        )
    normalized["dependencies"] = clean_dependencies

    normalized["generation_order"] = [
        item for item in normalized["generation_order"] if isinstance(item, str)
    ]

    return normalized


def _summarize_partial(
    partial_planning: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """
    Résume un planning partiel pour l'étape suivante.
    Si le LLM échoue, on retourne un fallback minimal.
    """
    prompt = build_summary_prompt(partial_planning)
    chain = _make_chain(prompt, model)

    try:
        response = chain.invoke({})
        summary = _extract_json_from_response(response)
        return summary
    except Exception as e:
        print(f"[planner] Résumé LLM échoué, fallback local. Détail: {e}")
        return {
            "project_name": partial_planning.get("project_name", ""),
            "description": partial_planning.get("description", ""),
            "folders": partial_planning.get("folders", []),
            "files": [
                {
                    "path": f.get("path", ""),
                    "type": f.get("type", ""),
                    "component_name": f.get("component_name", ""),
                }
                for f in partial_planning.get("files", [])
                if isinstance(f, dict)
            ],
        }


def _merge_plannings(
    partial_plannings: list[dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    """
    Fusionne plusieurs plannings partiels.
    """
    if len(partial_plannings) == 1:
        return _normalize_planning(partial_plannings[0])

    prompt = build_merge_prompt(partial_plannings)
    chain = _make_chain(prompt, model)
    response = chain.invoke({})
    merged = _extract_json_from_response(response)
    return _normalize_planning(merged)


def _run_single_call(
    payload: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    print("[planner] Stratégie: appel unique")
    prompt = build_single_call_prompt(payload)
    chain = _make_chain(prompt, model)
    response = chain.invoke({})
    planning = _extract_json_from_response(response)
    return _normalize_planning(planning)


def _run_chunked_calls(
    chunks: list[dict[str, Any]],
    reusable_components: list[dict[str, Any]],
    global_summary: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    print(f"[planner] Stratégie: chunking ({len(chunks)} chunks)")

    partial_plannings: list[dict[str, Any]] = []
    cumulative_summary: dict[str, Any] | None = None

    for i, chunk in enumerate(chunks, start=1):
        print(f"[planner] Chunk {i}/{len(chunks)} (scope: {chunk.get('chunk_scope', '?')})")

        current_chunk = chunk.get("current_chunk", chunk)

        if i == 1:
            prompt = build_first_chunk_prompt(
                chunk=current_chunk,
                reusable_components=reusable_components,
                global_summary=global_summary,
            )
        else:
            prompt = build_next_chunk_prompt(
                chunk=current_chunk,
                cumulative_summary=cumulative_summary or {},
                reusable_components=reusable_components,
                chunk_index=i,
                total_chunks=len(chunks),
            )

        chain = _make_chain(prompt, model)
        response = chain.invoke({})
        partial = _extract_json_from_response(response)
        partial = _normalize_planning(partial)
        partial_plannings.append(partial)

        if i < len(chunks):
            print(f"[planner] Résumé cumulatif après chunk {i}...")
            cumulative_summary = _summarize_partial(partial, model=model)

    print("[planner] Fusion des plannings partiels...")
    return _merge_plannings(partial_plannings, model)


def generate_planning(
    payload: dict[str, Any],
    chunks: list[dict[str, Any]] | None,
    global_summary: dict[str, Any],
    use_large_model: bool = False,
) -> dict[str, Any]:
    model = MODELS["large"] if use_large_model else MODELS["default"]
    reusable_components = payload.get("reusable_components", [])

    print(f"[planner] Démarrage génération planning (modèle: {model})")

    if not chunks:
        planning = _run_single_call(payload, model)
    else:
        planning = _run_chunked_calls(
            chunks=chunks,
            reusable_components=reusable_components,
            global_summary=global_summary,
            model=model,
        )

    print(
        f"[planner] Planning généré : "
        f"{len(planning.get('files', []))} fichiers, "
        f"{len(planning.get('folders', []))} dossiers"
    )
    return planning