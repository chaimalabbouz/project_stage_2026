import sys
from graphs.figma_planner_graph import graph

def main() -> None:
    initial_state = {"logs": []}
    final_state = {}

    print("🚀 DÉMARRAGE DU PIPELINE COMPLET...\n")
    print("🛑_DEBUG : DÉBUT DU STREAM...\n")

    try:
        for event in graph.stream(initial_state):
            for node_name, node_output in event.items():
                
                if node_output is None:
                    continue
                
                final_state.update(node_output)
                
                # DEBUG BASIQUE : On affiche TOUS les noeuds qui passent
                print(f"🛑_DEBUG : Noeud exécuté -> {node_name}")
                
                if "agent" in node_name.lower():
                    print(f"\n{'='*40}")
                    print(f"🧠 LANCEMENT DE : {node_name.upper()}")
                    print(f"{'='*40}")
                    
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            for tool in msg.tool_calls:
                                print(f"🔧 ACTION : {tool['name']}")
                        elif msg.type == "tool":
                            print(f"📥 RÉSULTAT : {str(msg.content)[:150]}...")
                        elif msg.type == "ai" and not hasattr(msg, 'tool_calls'):
                            print(f"✅ ÉTAPE TERMINÉE.")

    except Exception as e:
        print(f"\n\n❌ ERREUR GLOBALE : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n🛑_DEBUG : FIN DU STREAM NORMALE.\n")
    
    # Résumé
    print("="*50)
    print("=== Résumé d'exécution ===")
    for line in final_state.get("logs", []):
        print(line)
    print("="*50 + "\n")

if __name__ == "__main__":
    main()