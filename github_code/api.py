from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import base64
import requests
from datetime import datetime

app = FastAPI()

# === Configuration ===
PROJECT_OUTPUT_DIR = "/home/binitns/projet_stage/github_code/data2/output/my-app"


class GenerateRequest(BaseModel):
    user_name: str
    user_email: str
    github_login: str
    github_token: str  # ← Le token vient de l'extérieur
    figma_id: str

@app.get("/")
def root():
    return {"status": "API is running"}


@app.post("/generate")
def generate(request: GenerateRequest):
    print(f"Génération demandée par : {request.user_name} ({request.user_email})")
    
    # === 1. Lancer le pipeline Python ===
    result = subprocess.run(
        ["python", "main.py",request.figma_id],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return {
            "success": False,
            "step": "pipeline",
            "error": result.stderr
        }
    
    # === 2. Créer le repo GitHub ===
    repo_name = f"figma-to-react-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    headers = {
        "Authorization": f"Bearer {request.github_token}",
        "Accept": "application/vnd.github+json"
    }
    
    create_repo_response = requests.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json={
            "name": repo_name,
            "private": False,
            "auto_init": True
        }
    )
    
    if create_repo_response.status_code not in [200, 201]:
        return {
            "success": False,
            "step": "create_repo",
            "error": create_repo_response.json()
        }
    
    repo_data = create_repo_response.json()
    repo_full_name = repo_data["full_name"]
    repo_url = repo_data["html_url"]
    
    # === 3. Pousser tous les fichiers ===
    pushed_files = 0
    errors = []
    
    for root_dir, dirs, files in os.walk(PROJECT_OUTPUT_DIR):
        if "node_modules" in dirs:
            dirs.remove("node_modules")
        
        for filename in files:
            file_path = os.path.join(root_dir, filename)
            relative_path = os.path.relpath(file_path, PROJECT_OUTPUT_DIR)
            
            try:
                with open(file_path, "rb") as f:
                    content_base64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                errors.append(f"{relative_path}: {str(e)}")
                continue
            
            push_response = requests.put(
                f"https://api.github.com/repos/{repo_full_name}/contents/{relative_path}",
                headers=headers,
                json={
                    "message": f"Add {relative_path}",
                    "content": content_base64
                }
            )
            
            if push_response.status_code in [200, 201]:
                pushed_files += 1
            else:
                errors.append(f"{relative_path}: {push_response.json()}")
    
    return {
        "success": True,
        "message": "Tout est terminé !",
        "repo_url": repo_url,
        "files_pushed": pushed_files,
        "errors": errors
    }