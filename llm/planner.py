"""
llm/planner.py
==============
Appelle le LLM via LangChain pour générer le planning.
Inclut un retry si le JSON retourné est malformé.
"""

import json
import time
from typing import Any
from pathlib import Path

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import PLANNER_PLANNING_FILE

GROQ_MODEL = "moonshotai/kimi-k2-instruct"
MAX_RETRIES = 3

SYSTEM_PROMPT = """\
You are a frontend project planner. You receive a Figma design structure and a list of reusable components, and you produce a generation plan for a React + Vite + Tailwind CSS project.

Your job is to analyze the structure and output a JSON plan. Nothing else.

Rules:
1. Each top-level FRAME in the design canvas is a PAGE.
2. Each direct child of a page FRAME is a SECTION.
3. If the same section name appears in multiple pages (e.g. Header, Footer, Navbar), mark it as shared. Shared sections are generated once and reused across pages.
4. The generation_order must respect dependencies:
   - Reusable components first (they have no dependencies)
   - Then shared sections (they may use reusable components)
   - Then page-specific sections
   - Then pages (they assemble sections)

You MUST respond with ONLY a valid JSON object. No markdown, no explanation, no backticks, no comments.

The JSON schema:
{
  "pages": [
    {
      "page_name": "string",
      "page_id": "string",
      "sections": [
        {
          "section_name": "string",
          "section_id": "string"
        }
      ]
    }
  ],
  "shared_sections": ["string"],
  "generation_order": [
    {
      "type": "component | section | page",
      "name": "string",
      "shared": "boolean (only for sections)"
    }
  ]
}
"""


def _get_llm() -> ChatGroq:
    return ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=4096)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return response.content.strip()


def _parse_llm_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


def _build_user_prompt(planner_input: dict[str, Any]) -> str:
    chunks = planner_input.get("chunks", [])
    stats = planner_input.get("stats", {})
    parts = []
    parts.append("## Project Stats")
    parts.append(json.dumps(stats, indent=2))
    parts.append("\n## Design Structure")
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            parts.append(f"\n### Chunk {i + 1}")
        if "canvases" in chunk:
            parts.append(json.dumps(chunk["canvases"], indent=2))
        elif "frame" in chunk:
            parts.append(json.dumps(chunk["frame"], indent=2))
    if chunks:
        components = chunks[0].get("reusable_components", [])
        if components:
            parts.append("\n## Reusable Components Available")
            parts.append(json.dumps(components, indent=2))
    parts.append("\n## Task")
    parts.append("Produce the generation plan JSON. ONLY valid JSON, nothing else.")
    return "\n".join(parts)


def _validate_planning(planning: dict) -> dict:
    if "pages" not in planning:
        raise ValueError("Planning manque 'pages'")
    if "generation_order" not in planning:
        raise ValueError("Planning manque 'generation_order'")
    for page in planning["pages"]:
        if "page_name" not in page:
            raise ValueError(f"Page sans 'page_name': {page}")
        if "sections" not in page:
            raise ValueError(f"Page '{page.get('page_name')}' sans 'sections'")
    return planning


def generate_planning(
    planner_input: dict[str, Any],
    output_path: Path = PLANNER_PLANNING_FILE,
) -> dict[str, Any]:
    print("[planner] Construction du prompt...")
    user_prompt = _build_user_prompt(planner_input)
    print(f"[planner] Taille du prompt : {len(user_prompt)} caractères")

    # Retry si JSON malformé
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[planner] Appel LLM (tentative {attempt}/{MAX_RETRIES})...")
            raw_response = _call_llm(SYSTEM_PROMPT, user_prompt)
            planning = _parse_llm_json(raw_response)
            planning = _validate_planning(planning)
            break  # Succès
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[planner] ⚠️ Erreur parsing/validation : {e}")
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Le LLM n'a pas retourné de JSON valide après {MAX_RETRIES} tentatives.") from e
            print(f"[planner] Retry dans 2 secondes...")
            time.sleep(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(planning, f, ensure_ascii=False, indent=2)

    print(f"[planner] Planning : {len(planning['pages'])} pages, "
          f"{len(planning.get('shared_sections', []))} shared, "
          f"{len(planning['generation_order'])} étapes")
    print(f"[planner] Sauvegardé -> {output_path}")
    return planning