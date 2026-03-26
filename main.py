from graphs.figma_planner_graph import graph


def main() -> None:
    result = graph.invoke({
        "logs": [],
    })

    print("\n=== Résumé d'exécution ===")
    for line in result.get("logs", []):
        print(line)

    print("\n=== Décision planner ===")
    print(f"chunk_strategy         : {result.get('chunk_strategy')}")
    print(f"large_model_required   : {result.get('large_model_required')}")
    print(f"planner_payload_chars  : {result.get('planner_payload_chars')}")
    print(f"estimated_tokens       : {result.get('planner_payload_estimated_tokens')}")
    print(f"chunk_count            : {result.get('chunk_count', 0)}")


if __name__ == "__main__":
    main()