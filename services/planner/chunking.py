from typing import Any

from services.planner.size_estimator import estimate_json_size


def _wrap_chunk(
    global_summary: dict[str, Any],
    reusable_components: list[dict[str, Any]],
    current_chunk: dict[str, Any],
    scope: str,
) -> dict[str, Any]:
    return {
        "global_summary": global_summary,
        "reusable_components": reusable_components,
        "chunk_scope": scope,
        "current_chunk": current_chunk,
    }


def _split_canvas_into_frame_chunks(
    canvas: dict[str, Any],
    global_summary: dict[str, Any],
    reusable_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    children = canvas.get("children", [])

    if not children:
        return [
            _wrap_chunk(global_summary, reusable_components, canvas, "single_canvas")
        ]

    if len(children) > 1:
        return [
            _wrap_chunk(
                global_summary=global_summary,
                reusable_components=reusable_components,
                current_chunk=child,
                scope=f"canvas_child:{child.get('name', 'unknown')}",
            )
            for child in children
        ]

    root = children[0]
    root_children = root.get("children", [])

    if len(root_children) > 1:
        return [
            _wrap_chunk(
                global_summary=global_summary,
                reusable_components=reusable_components,
                current_chunk=child,
                scope=f"root_frame_child:{child.get('name', 'unknown')}",
            )
            for child in root_children
        ]

    return [
        _wrap_chunk(global_summary, reusable_components, root, "single_root_frame")
    ]


def _structural_subsplit_if_needed(
    chunk: dict[str, Any],
    max_chars_per_chunk: int,
) -> list[dict[str, Any]]:
    size = estimate_json_size(chunk)
    if size["chars"] <= max_chars_per_chunk:
        return [chunk]

    current = chunk.get("current_chunk", {})
    children = current.get("children", [])

    if not children or len(children) <= 1:
        return [chunk]

    subchunks = []
    for child in children:
        sub = {
            "global_summary": chunk["global_summary"],
            "reusable_components": chunk["reusable_components"],
            "chunk_scope": f"{chunk.get('chunk_scope', 'unknown')} -> child:{child.get('name', 'unknown')}",
            "current_chunk": child,
        }
        subchunks.append(sub)

    return subchunks


def build_structural_chunks(
    planner_payload: dict[str, Any],
    global_summary: dict[str, Any],
    max_chars_per_chunk: int,
) -> list[dict[str, Any]]:
    figma_tree = planner_payload.get("figma_tree", {})
    canvases = figma_tree.get("document", {}).get("children", [])
    reusable_components = planner_payload.get("reusable_components", [])

    if not canvases:
        return []

    initial_chunks: list[dict[str, Any]] = []

    if len(canvases) > 1:
        for canvas in canvases:
            initial_chunks.append(
                _wrap_chunk(
                    global_summary=global_summary,
                    reusable_components=reusable_components,
                    current_chunk=canvas,
                    scope=f"canvas:{canvas.get('name', 'unknown')}",
                )
            )
    else:
        initial_chunks.extend(
            _split_canvas_into_frame_chunks(
                canvas=canvases[0],
                global_summary=global_summary,
                reusable_components=reusable_components,
            )
        )

    final_chunks: list[dict[str, Any]] = []
    for chunk in initial_chunks:
        final_chunks.extend(
            _structural_subsplit_if_needed(
                chunk=chunk,
                max_chars_per_chunk=max_chars_per_chunk,
            )
        )

    return final_chunks


    """
    Rôle :

découper le payload si nécessaire
règles :
plusieurs canvases → chunk par canvas
un seul canvas → chunk par grandes frames
si un chunk reste gros → sous-découpage structurel

 c’est la logique de chunking.
"""