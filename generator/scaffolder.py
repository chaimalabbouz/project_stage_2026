import subprocess
import shutil
from pathlib import Path
from typing import Any


def _run_cmd(cmd: list[str], cwd: Path, timeout: int = 180) -> bool:
    """Exécute une commande shell silencieusement, retourne True si succès."""
    try:
        subprocess.run(
            cmd,
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[Scaffolder] Erreur commande {' '.join(cmd)} :\n{e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        print(f"[Scaffolder] Timeout commande {' '.join(cmd)}")
        return False


def create_project_files(project_path: Path) -> None:
    """Crée tous les fichiers nécessaires pour un projet React + Vite."""
    
    # Créer le dossier src AVANT d'écrire les fichiers dedans
    (project_path / "src").mkdir(parents=True, exist_ok=True)
    
    # 1. package.json
    (project_path / "package.json").write_text(
        '''{
  "name": "e-commerce-home",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.17",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "vite": "^5.1.0"
  }
}''',
        encoding="utf-8"
    )
    
    # 2. index.html
    (project_path / "index.html").write_text(
        '''<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>E-commerce Home</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>''',
        encoding="utf-8"
    )
    
    # 3. vite.config.js
    (project_path / "vite.config.js").write_text(
        '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true
  }
})''',
        encoding="utf-8"
    )
    
    # 4. tailwind.config.js
    (project_path / "tailwind.config.js").write_text(
        '''/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}''',
        encoding="utf-8"
    )
    
    # 5. postcss.config.js
    (project_path / "postcss.config.js").write_text(
        '''export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}''',
        encoding="utf-8"
    )
    
    # 6. .gitignore
    (project_path / ".gitignore").write_text(
        '''# Dependencies
node_modules/
.pnp/
.pnp.js

# Testing
coverage/

# Production
dist/
dist-ssr/
*.local

# Editor
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db''',
        encoding="utf-8"
    )
    
    # 7. src/main.jsx
    (project_path / "src" / "main.jsx").write_text(
        '''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)''',
        encoding="utf-8"
    )
    
    # 8. src/App.jsx
    (project_path / "src" / "App.jsx").write_text(
        '''import HomePage from './pages/HomePage'

function App() {
  return <HomePage />
}

export default App''',
        encoding="utf-8"
    )
    
    # 9. src/App.css
    (project_path / "src" / "App.css").write_text(
        '''* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}''',
        encoding="utf-8"
    )
    
    # 10. src/index.css (avec Tailwind)
    (project_path / "src" / "index.css").write_text(
        '''@tailwind base;
@tailwind components;
@tailwind utilities;''',
        encoding="utf-8"
    )


def setup_project(project_path: Path, planning: dict[str, Any]) -> bool:
    """Crée le projet React + Vite + Tailwind et installe les dépendances."""
    print(f"\n[Scaffolder] Initialisation du projet dans : {project_path}")

    # Vérifier que npm est disponible
    if not shutil.which("npm"):
        print("[Scaffolder] ERREUR FATALE : 'npm' introuvable.")
        print("[Scaffolder] Installe Node.js : https://nodejs.org/")
        return False

    # S'assurer que le dossier parent existe
    project_path.parent.mkdir(parents=True, exist_ok=True)

    # Supprimer si le projet existe déjà
    if project_path.exists():
        print(f"[Scaffolder] Suppression de l'ancien dossier...")
        shutil.rmtree(project_path)

    # Créer le dossier principal
    project_path.mkdir(parents=True, exist_ok=True)

    # Créer tous les fichiers du projet
    print("[Scaffolder] Création des fichiers du projet...")
    create_project_files(project_path)

    # Installer les dépendances
    print("[Scaffolder] Installation des dépendances (1-2 minutes)...")
    if not _run_cmd(["npm", "install"], cwd=project_path, timeout=300):
        print("[Scaffolder] ÉCHEC : impossible d'installer les dépendances.")
        return False

    # Dépendances supplémentaires du planning
    dependencies = planning.get("dependencies", [])
    if dependencies:
        packages = [dep["package"] for dep in dependencies if dep.get("package")]
        if packages:
            print(f"[Scaffolder] Installation des packages : {', '.join(packages)}")
            _run_cmd(["npm", "install"] + packages, cwd=project_path, timeout=300)

    # Création de l'arborescence
    for folder in planning.get("folders", []):
        folder_path = project_path / folder.get("path", "")
        folder_path.mkdir(parents=True, exist_ok=True)

    print("[Scaffolder] ✅ Projet initialisé avec succès !")
    return True