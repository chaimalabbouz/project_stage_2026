import json
import subprocess
import sys
from pathlib import Path
from config.settings import OUTPUT_DIR

# Nom du projet React généré
PROJECT_NAME = "my-app"
PROJECT_DIR = OUTPUT_DIR / PROJECT_NAME


def _create_folders() -> None:
    """Crée la structure de dossiers du projet React."""
    folders = [
        PROJECT_DIR / "src" / "components",
        PROJECT_DIR / "src" / "pages",
        PROJECT_DIR / "src" / "assets",
        PROJECT_DIR / "public",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    print(f"[setup] Dossiers créés -> {PROJECT_DIR}")


def _write_package_json(external_deps: list[str]) -> None:
    """Génère package.json avec les dépendances détectées."""

    # Dépendances de base
    dependencies = {
        "react": "^18.2.0",
        "react-dom": "^18.2.0",
        "react-router-dom": "^6.22.0",
    }

    # Ajouter les dépendances externes détectées par l'architecte
    if "@mui/material" in external_deps:
        dependencies["@mui/material"] = "^5.15.0"
        dependencies["@emotion/react"] = "^11.11.0"
        dependencies["@emotion/styled"] = "^11.11.0"
    if "@mui/icons-material" in external_deps:
        dependencies["@mui/icons-material"] = "^5.15.0"

    package = {
        "name": PROJECT_NAME,
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "dev": "vite",
            "build": "tsc && vite build",
            "preview": "vite preview",
        },
        "dependencies": dependencies,
        "devDependencies": {
            "@types/react": "^18.2.0",
            "@types/react-dom": "^18.2.0",
            "@vitejs/plugin-react": "^4.2.0",
            "typescript": "^5.2.0",
            "vite": "^5.1.0",
            "tailwindcss": "^3.4.0",
            "autoprefixer": "^10.4.0",
            "postcss": "^8.4.0",
        },
    }

    with open(PROJECT_DIR / "package.json", "w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)
    print(f"[setup] package.json créé avec {len(dependencies)} dépendances")


def _write_tsconfig() -> None:
    tsconfig = {
        "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": True,
            "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext",
            "skipLibCheck": True,
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": True,
            "resolveJsonModule": True,
            "isolatedModules": True,
            "noEmit": True,
            "jsx": "react-jsx",
            "strict": True,
            "noUnusedLocals": True,
            "noUnusedParameters": True,
            "noFallthroughCasesInSwitch": True,
            "baseUrl": ".",
            "paths": {"@/*": ["./src/*"]},
        },
        "include": ["src"],
        "references": [{"path": "./tsconfig.node.json"}],
    }
    with open(PROJECT_DIR / "tsconfig.json", "w", encoding="utf-8") as f:
        json.dump(tsconfig, f, indent=2, ensure_ascii=False)
    print("[setup] tsconfig.json créé")


def _write_tailwind_config() -> None:
    content = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
"""
    with open(PROJECT_DIR / "tailwind.config.js", "w", encoding="utf-8") as f:
        f.write(content)
    print("[setup] tailwind.config.js créé")


def _write_vite_config() -> None:
    content = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
"""
    with open(PROJECT_DIR / "vite.config.ts", "w", encoding="utf-8") as f:
        f.write(content)
    print("[setup] vite.config.ts créé")


def _write_index_html() -> None:
    content = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>My App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""
    with open(PROJECT_DIR / "public" / "index.html", "w", encoding="utf-8") as f:
        f.write(content)
    with open(PROJECT_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("[setup] index.html créé")


def _write_main_tsx() -> None:
    content = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
"""
    with open(PROJECT_DIR / "src" / "main.tsx", "w", encoding="utf-8") as f:
        f.write(content)
    print("[setup] src/main.tsx créé")


def _write_index_css() -> None:
    content = """@tailwind base;
@tailwind components;
@tailwind utilities;
"""
    with open(PROJECT_DIR / "src" / "index.css", "w", encoding="utf-8") as f:
        f.write(content)
    print("[setup] src/index.css créé")



def _route_from_page_name(name: str) -> str:
    import re
    parts = re.findall(r"[A-Za-z0-9]+", name)
    slug = "-".join(p.lower() for p in parts)
    return "/" if slug in ("home", "accueil", "index") else f"/{slug}"


def _write_app_tsx(pages: list[dict]) -> None:
    imports = "\n".join(
        f"import {p['name']} from './pages/{p['name']}'"
        for p in pages
    )

    routes = []
    for i, p in enumerate(pages):
        path = "/" if i == 0 else _route_from_page_name(p["name"])
        routes.append(f'        <Route path="{path}" element={{<{p["name"]} />}} />')

    content = f"""import React from 'react'
import {{ BrowserRouter, Routes, Route }} from 'react-router-dom'
{imports}

function App() {{
  return (
    <BrowserRouter>
      <Routes>
{chr(10).join(routes)}
      </Routes>
    </BrowserRouter>
  )
}}

export default App
"""
    with open(PROJECT_DIR / "src" / "App.tsx", "w", encoding="utf-8") as f:
        f.write(content)

    print("[setup] src/App.tsx créé avec routing")



def _sanitize_component_name(name: str) -> str:
    import re
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    cleaned = "".join(p[0].upper() + p[1:] for p in parts if p)
    return cleaned or "Component"


def _sanitize_page_name(name: str) -> str:
    import re
    parts = re.split(r'[^a-zA-Z0-9]+', name)
    cleaned = "".join(p[0].upper() + p[1:] for p in parts if p)
    return cleaned or "Page"


def _write_placeholder_files(analyse: dict, architecture: dict) -> None:
    """Crée des fichiers .tsx vides pour chaque composant et page."""

    # Composants réutilisables
    for comp in architecture.get("components", []):
        original_name = comp["name"]
        safe_name = _sanitize_component_name(original_name)

        file_path = PROJECT_DIR / "src" / "components" / f"{safe_name}.tsx"
        file_path.write_text(
            f"// {safe_name} — sera généré par le LLM\n"
            f"export default function {safe_name}() {{ return null }}\n",
            encoding="utf-8",
        )

    # Pages
    for page in analyse.get("pages", []):
        original_name = page["name"]
        safe_name = _sanitize_page_name(original_name)

        file_path = PROJECT_DIR / "src" / "pages" / f"{safe_name}.tsx"
        file_path.write_text(
            f"// {safe_name} — sera généré par le LLM\n"
            f"export default function {safe_name}() {{ return null }}\n",
            encoding="utf-8",
        )

    print("[setup] Fichiers placeholder créés")

def _collect_external_deps(architecture: dict) -> list[str]:
    """Collecte toutes les dépendances externes détectées par l architecte."""
    deps = set()
    for comp in architecture.get("components", []):
        for dep in comp.get("external_deps", []):
            deps.add(dep)
    return list(deps)


def run_setup() -> Path:
    """Point d entrée principal du setup."""
    print("\n[setup] Démarrage du setup du projet React...")

    # Charger analyse et architecture
    analyse_path = OUTPUT_DIR.parent / "plans" / "analyse.json"
    architecture_path = OUTPUT_DIR.parent / "plans" / "architecture.json"

    with open(analyse_path, "r", encoding="utf-8") as f:
        analyse = json.load(f)
    with open(architecture_path, "r", encoding="utf-8") as f:
        architecture = json.load(f)

    external_deps = _collect_external_deps(architecture)
    print(f"[setup] Dépendances externes détectées : {external_deps}")

    # Créer la structure
    _create_folders()
    _write_package_json(external_deps)
    _write_tsconfig()
    _write_tailwind_config()
    _write_vite_config()
    _write_index_html()
    _write_main_tsx()
    _write_index_css()
    _write_app_tsx(analyse.get("pages", []))
    _write_placeholder_files(analyse, architecture)

    print(f"\n[setup] Projet React créé -> {PROJECT_DIR}")
    print(f"[setup] Pour lancer : cd {PROJECT_DIR} && npm install && npm run dev")

    return PROJECT_DIR


if __name__ == "__main__":
    run_setup()