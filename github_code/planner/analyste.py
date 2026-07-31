import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_API_KEY, ANALYSE_OUTPUT_FILE, INPUT_PLANNER_FILE
from db.prompt_loader import get_prompt_config


def run_analyste() -> dict:
    print("\n[analyste] Chargement du payload...")

    # Charger la configuration depuis la base de données
    print("[analyste] Chargement du prompt depuis la base...")
    config = get_prompt_config("architecte_structure_pages")
    
    SYSTEM_PROMPT = config['prompt']
    MODEL = config['model_name']
    TEMPERATURE = config['temperature']
    MAX_TOKENS = config['max_tokens'] if config['max_tokens'] else None

    print(f"[analyste] Modèle utilisé: {MODEL}")
    

    with open(INPUT_PLANNER_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    

    llm = ChatGroq(
        model=MODEL,
        api_key=GROQ_API_KEY,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Voici les donnees Figma :\n\n{payload_str}"),
    ]

    response = llm.invoke(messages)
    raw_text = response.content.strip()

    # Afficher la réponse brute pour déboguer
    

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

   

    return analyse