import json
from config.settings import TREE_OUTPUT_FILE, COMPONENT_REU_OUTPUT_FILE, INPUT_PLANNER_FILE


def prepare_payload() -> dict:
    print("\n[prepare_payload] Chargement des fichiers extraits...")

    with open(TREE_OUTPUT_FILE, "r", encoding="utf-8") as f:
        tree = json.load(f)

    with open(COMPONENT_REU_OUTPUT_FILE, "r", encoding="utf-8") as f:
        reu_data = json.load(f)

    # Construire la liste légère des composants pour l'analyste
    # Standalone : un composant = une entrée
    # Variant set : le set entier = une entrée avec ses props de variantes
    reusable_lightweight = []

    for comp in reu_data.get("standalone", []):
        reusable_lightweight.append({
            "component_id": comp["component_id"],
            "name": comp["name"],
            "kind": "standalone",
        })

    for vset in reu_data.get("variant_sets", []):
        variant_ids = [v["component_id"] for v in vset.get("variants", [])]
        variant_props = {
            prop_name: prop_data.get("options", [])
            for prop_name, prop_data in vset.get("props", {}).items()
            if prop_data.get("type") == "VARIANT"
        }
        reusable_lightweight.append({
            "component_set_id": vset["component_set_id"],
            "name": vset["name"],
            "kind": "variant_set",
            "variant_component_ids": variant_ids,
            "variant_props": variant_props,
        })

    payload = {
        "figma_tree": tree,
        "reusable_components": reusable_lightweight,
    }

    INPUT_PLANNER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INPUT_PLANNER_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    size_kb = INPUT_PLANNER_FILE.stat().st_size / 1024
    chars = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"[prepare_payload] Sauvegardé -> {INPUT_PLANNER_FILE}")
    print(f"[prepare_payload] Taille : {size_kb:.1f} KB — {chars} caractères")

    return payload