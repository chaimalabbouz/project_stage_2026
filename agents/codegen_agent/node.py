import json
import os
from pathlib import Path
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

# --- Récupération de la clé API ---
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Chemins des données ---
PLANNING_FILE = Path("data/planner/planning.json")
COMPONENTS_STYLE_FILE = Path("data/code_style/component_reu.json")
PROCESSED_TREE_FILE = Path("data/code_style/processed.json")
BASE_OUTPUT_DIR = Path("data/generated_projects/fintech_landing")

MODEL_NAME = "moonshotai/kimi-k2-instruct-0905"

# ==============================================================================
# PROMPTS SYSTÈMES
# ==============================================================================


PROMPT_COMPONENT = """
Tu es un expert React JSX. Tu reçois le JSON d'un composant avec ses classes Tailwind.
Règles STRICTES :
- PAS de markdown. Export par défaut : export default function NomComposant() { return ( ... ); }
- Utilise exactement les "tailwind_classes" trouvées.
- Transforme les "characters" en props logiques.
- Les images (type IMAGE) -> <img src="/placeholder.jpg" alt="img" className="[classes]" />
- Les icônes (type VECTOR) -> <div className="[classes]"> </div> (GARDE les vectors !)
"""

PROMPT_SECTION = """
Tu es un expert React JSX. Tu reçois le JSON d'une section avec ses classes Tailwind.
Règles STRICTES :
- PAS de markdown. Export par défaut : export default function NomSection() { return ( ... ); }
- Utilise exactement les "tailwind_classes" du JSON.
- Les images (type IMAGE) -> <img src="/placeholder.jpg" alt="img" className="[classes]" />
- Les icônes (type VECTOR) -> <div className="[classes]">★</div> (GARDE les vectors !)

RÈGLES D'IMPORTS TOTALEMENT INTERDITES DE VIOLER :
- Tu as le droit d'importer UNIQUEMENT les composants listés dans la phrase "Dépendances à importer : [...]".
- Si tu vois un "componentId" dans le JSON MAIS qu'il N'EST PAS dans la liste des dépendances, tu NE DOIS PAS l'importer. 
- Dans ce cas, transforme ce nœud en un simple <div className="[ses_tailwind_classes]">...</div> au lieu d'un composant.
"""

PROMPT_PAGE = """
Assemble une page React. Règles : PAS de markdown. Export par défaut.
Importe les dépendances listées (ex: import X from '../components/X' ou '../sections/X').
Structure : export default function Page() { return ( <> <Comp1 /> <Comp2 /> </> ); }
"""
# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def _clean_llm_output(raw_text: str) -> str:
    """Enlève les balises markdown si l'IA en met."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    return text

def _compact_json(data: dict) -> str:
    """
    SUPPRIME LES ESPACES ET SAUTS DE LIGNE.
    Réduit la taille du message envoyé à l'IA de 40% sans perdre de données.
    """
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

def _extract_subtree(full_tree: dict, target_id: str) -> dict | None:
    """Cherche un noeud précis par son ID dans l'arbre géant processed.json."""
    if full_tree.get("id") == target_id:
        return full_tree
    for child in full_tree.get("children", []):
        result = _extract_subtree(child, target_id)
        if result:
            return result
    return None

def _get_file_metadata(planning: dict, file_path: str) -> dict | None:
    """Récupère les métadonnées d'un fichier depuis planning.json."""
    for f in planning.get("files", []):
        if f.get("path") == file_path:
            return f
    return None

def _find_component_style(all_components: dict, component_id: str) -> dict | None:
    """Cherche le style pré-calculé d'un composant réutilisable."""
    for comp in all_components.get("components", []):
        if comp.get("component_id") == component_id:
            return comp
    return None


# ==============================================================================
# LE NOEUD LANGGRAPH PRINCIPAL
# ==============================================================================

def codegen_node(state: dict) -> dict:
    print("\n" + "="*50)
    print("[🤖 CODEGEN AGENT] Démarrage de la génération de code...")
    print("="*50)
    logs = list(state.get("logs", []))

    # 1. Chargement des données
    with open(PLANNING_FILE, "r", encoding="utf-8") as f:
        planning = json.load(f)
    with open(COMPONENTS_STYLE_FILE, "r", encoding="utf-8") as f:
        components_style = json.load(f)
    with open(PROCESSED_TREE_FILE, "r", encoding="utf-8") as f:
        processed_data = json.load(f)

    tree_root = processed_data.get("document", processed_data)

    # 2. Initialisation du LLM
    llm = ChatGroq(
        model=MODEL_NAME,
        api_key=GROQ_API_KEY,
        temperature=0,
    )

    # 3. Boucle sur l'ordre de génération dicté par le Planner
    generation_order = planning.get("generation_order", [])

    for file_path in generation_order:
        meta = _get_file_metadata(planning, file_path)
        if not meta:
            logs.append(f"[Codegen] ⚠️ Métadonnées manquantes pour {file_path}")
            continue

        comp_name = meta.get("component_name", "Unknown")
        file_type = meta.get("type") # "component", "section", "page"
        figma_id = meta.get("figma_node_id")
        depends_on = meta.get("depends_on", [])
        
        target_file = BASE_OUTPUT_DIR / file_path
        logs.append(f"[Codegen] Génération {file_type} : {comp_name}...")

        try:
            # ---------------------------------------------------------
            # LOGIQUE DE GÉNÉRATION DIFFÉRENCIÉE
            # ---------------------------------------------------------
            
            if file_type == "component" and figma_id:
                # CAS 1 : Composant réutilisable -> On cherche dans component_reu.json
                component_data = _find_component_style(components_style, figma_id)
                
                if not component_data:
                    logs.append(f"[Codegen] ⚠️ Style introuvable pour {comp_name}")
                    continue

                # On compacte le JSON pour éviter l'erreur 413
                payload_str = _compact_json(component_data.get("definition", {}))
                user_msg = f"Génère le composant React '{comp_name}' basé sur cette structure Figma :\n\n{payload_str}"
                
                response = llm.invoke([
                    SystemMessage(content=PROMPT_COMPONENT),
                    HumanMessage(content=user_msg)
                ])

            elif file_type == "section" and figma_id:
                # CAS 2 : Section -> On extrait juste cette section du gros processed.json
                subtree = _extract_subtree(tree_root, figma_id)
                
                if not subtree:
                    logs.append(f"[Codegen] ⚠️ Noeud {figma_id} introuvable dans processed.json")
                    continue

                # On compacte le sous-arbre
                payload_str = _compact_json(subtree)
                context_deps = f"Dépendances à importer : {depends_on}." if depends_on else ""
                
                user_msg = f"Génère la section React '{comp_name}'. {context_deps}\n\nVoici l'arbre Figma :\n\n{payload_str}"
                
                response = llm.invoke([
                    SystemMessage(content=PROMPT_SECTION),
                    HumanMessage(content=user_msg)
                ], max_tokens=8000)

            elif file_type == "page":
                # CAS 3 : Page -> AUCUN JSON FIGMA. Juste l'assemblage des dépendances !
                payload = {
                    "page_name": comp_name,
                    "depends_on": depends_on
                }
                payload_str = _compact_json(payload)
                
                user_msg = f"Assemble la page React '{comp_name}' en important et rendant ces éléments :\n\n{payload_str}"
                
                response = llm.invoke([
                    SystemMessage(content=PROMPT_PAGE),
                    HumanMessage(content=user_msg)
                ])

            else:
                logs.append(f"[Codegen] ⚠️ Type inconnu pour {file_path}")
                continue

            # ---------------------------------------------------------
            # SAUVEGARDE DU FICHIER
            # ---------------------------------------------------------
            code = _clean_llm_output(response.content)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(code)
                
            logs.append(f"[Codegen] ✅ Succès -> {target_file.name} ({len(code)} chars)")

        except Exception as e:
            error_msg = str(e)
            # Si on a encore une erreur de taille (très rare maintenant), on le signale sans crasher
            if "413" in error_msg or "tokens" in error_msg.lower():
                logs.append(f"[Codegen] ❌ Erreur de taille (Trop gros même compacté) pour {comp_name}. Ignoré.")
            else:
                logs.append(f"[Codegen] ❌ Erreur inattendue pour {comp_name} : {error_msg}")
            continue

    logs.append("[Codegen] 🏁 Génération terminée.")
    print("\n[🤖 CODEGEN AGENT] Terminé !\n")

    return {"logs": logs}