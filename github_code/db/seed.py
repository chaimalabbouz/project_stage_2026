# seed_prompt3.py
from db.db import get_connection

SYSTEM_PROMPT_3 = """
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
  déterminée par l extraction, tu ne dois pas la modifier (c'est pour donner l architecture)
""".strip()

def seed_prompt3():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO prompts (nom_prompt, prompt, version)
        VALUES (%s, %s, %s)
    """, ("architecte_structure_pages", SYSTEM_PROMPT_3, 1))
    
    prompt_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO model_prompt_config (model_id, prompt_id, temperature, max_tokens)
        VALUES (%s, %s, %s, %s)
    """, (1, prompt_id, 0, None))
    
    conn.commit()
    conn.close()
    
    print(f"✅ 3ème prompt ajouté")
    print(f"   - ID: {prompt_id}")
    print(f"   - Nom: architecte_structure_pages")
    print(f"   - model_id: 1")
    print(f"   - temperature: 0")
    print(f"   - max_tokens: NULL (vide)")

if __name__ == "__main__":
    seed_prompt3()
"""
 python -m db.seed
 """    