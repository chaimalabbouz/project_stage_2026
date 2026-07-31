# db/prompt_loader.py
from db.db import get_connection

def get_prompt_config(nom_prompt):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            p.prompt,
            m.model_name,
            m.provider,
            mpc.temperature,
            mpc.max_tokens
        FROM prompts p
        JOIN model_prompt_config mpc ON p.id = mpc.prompt_id
        JOIN models m ON mpc.model_id = m.id
        WHERE p.nom_prompt = %s
    """, (nom_prompt,))
    
    config = cursor.fetchone()
    conn.close()
    
    if not config:
        raise Exception(f"Prompt '{nom_prompt}' non trouvé dans la base")
    
    return config