import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_API_KEY, ANALYSE_OUTPUT_FILE, INPUT_PLANNER_FILE, MODEL

SYSTEM_PROMPT = """
Tu es un expert en architecture React.
Tu reçois deux JSONs :
1. L arbre Figma limité à 3 niveaux
2. La liste COMPLÈTE des composants réutilisables (standalone + variant sets)

Tu dois retourner UNIQUEMENT un JSON valide, sans texte avant ou après, sans balises markdown.

Structure exacte attendue :
{
  "pages": [
    {
      "id": "id figma exact",
      "name": "NomDeLaPage",
      "suggested_file": "src/pages/NomDeLaPage.tsx",
      "components_used": ["Header", "ProductCard", "Footer"]
    }
  ],
  "project_structure": {
    "src/pages": ["liste des fichiers pages"],
    "src/components": ["liste des fichiers composants"]
  },
  "summary": {
    "total_pages": 0,
    "total_components": 0
  }
}

Règles :
- Garder les id Figma exacts
- PascalCase pour les noms de composants et pages
- Ne pas inventer des éléments qui n existent pas dans les JSONs
- Les variant sets (kind: "variant_set") sont UN SEUL composant React avec des props
  Exemple : un variant set "Buttons" avec variant_props {Size: ["Small", "Large"]}
  → un seul composant React "Buttons" avec une prop size
- NE PAS retourner de champ "reusable_components" — la liste des composants est déjà
  déterminée par l extraction, tu ne dois pas la modifier
- Tu dois UNIQUEMENT planifier les pages
""".strip()


def run_analyste() -> dict:
    print("\n[analyste] Chargement du payload...")

    with open(INPUT_PLANNER_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    print(f"[analyste] {len(payload_str)} caractères envoyés au LLM.")
    print(f"[analyste] Envoi au modele {MODEL}...")

    llm = ChatGroq(
        model=MODEL,
        api_key=GROQ_API_KEY,
        temperature=0,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Voici les donnees Figma :\n\n{payload_str}"),
    ]

    response = llm.invoke(messages)
    raw_text = response.content.strip()

    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1]).strip()

    try:
        analyse = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"[analyste] JSON invalide : {e}\nReponse brute :\n{raw_text[:500]}")

    ANALYSE_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ANALYSE_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(analyse, f, ensure_ascii=False, indent=2)

    summary = analyse.get("summary", {})
    print(f"[analyste] Planning termine :")
    print(f"  - Pages      : {summary.get('total_pages', '?')}")
    print(f"  - Composants : {summary.get('total_components', '?')}")
    print(f"[analyste] Sauvegarde -> {ANALYSE_OUTPUT_FILE}")

    return analyse