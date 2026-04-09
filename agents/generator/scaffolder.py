import json
from pathlib import Path

PLANNING_FILE = Path("data/planner/planning.json")
BASE_OUTPUT_DIR = Path("data/generated_projects")


def _generate_app_router(planning: dict, project_dir: Path):
    """Génère le fichier App.jsx avec les routes React configurées."""
    routes = planning.get("routes", [])

    imports = []
    route_elements = []

    for route in routes:
        comp_name = route["page_component"]
        rel_path = route["file_path"].replace("src/", "./").replace(".jsx", "")
        path_val = route["path"]

        imports.append(f"import {comp_name} from '{rel_path}';")
        route_elements.append(
            '          <Route path="{}" element={{<{}/>}} />'.format(path_val, comp_name)
        )

    imports_code = "\n".join(imports)
    routes_code = "\n".join(route_elements)

    app_content = f"""import {{ BrowserRouter, Routes, Route }} from 'react-router-dom';
{imports_code}

function App() {{
  return (
    <BrowserRouter>
      <Routes>
{routes_code}
      </Routes>
    </BrowserRouter>
  );
}}

export default App;
"""
    with open(project_dir / "src" / "App.jsx", "w", encoding="utf-8") as f:
        f.write(app_content)

    print(f"[✅ Scaffolder] src/App.jsx généré avec {len(routes)} route(s).")


def _inject_google_fonts(project_dir: Path):
    """Injecte automatiquement les polices Google dans le index.html généré."""
    html_file = project_dir / "index.html"
    if not html_file.exists():
        return

    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Le bout de code HTML à injecter
    font_link = """    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@100..1000&family=Inter:wght@100..900&family=Poppins:wght@100..900&display=swap" rel="stylesheet">
"""

    # On l'insère juste avant la fermeture de <head> si ce n'est pas déjà fait
    if "</head>" in content and "fonts.googleapis.com" not in content:
        content = content.replace("</head>", f"{font_link}\n  </head>")
        
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(content)
        print("[✅ Scaffolder] Polices Google injectées dans index.html")


def scaffold_project_node(state: dict) -> dict:
    print("\n[🏗️ Scaffolder] Vérification du projet React existant...")

    if not PLANNING_FILE.exists():
        return {"logs": ["[Scaffolder] ❌ planning.json introuvable."]}

    with open(PLANNING_FILE, "r", encoding="utf-8") as f:
        planning = json.load(f)

    project_name = "fintech_landing"
    project_dir = BASE_OUTPUT_DIR / project_name
    logs = []

    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ✅ ON NE CRÉE PLUS LE PROJET ICI
    if not project_dir.exists():
        return {
            "logs": [
                f"[Scaffolder] ❌ Projet {project_dir} introuvable.",
                "[Scaffolder] Crée d'abord le projet Vite manuellement puis relance le pipeline."
            ]
        }

    package_json = project_dir / "package.json"
    src_dir = project_dir / "src"
    vite_config = project_dir / "vite.config.js"

    if not package_json.exists():
        return {
            "logs": [
                f"[Scaffolder] ❌ package.json introuvable dans {project_dir}.",
                "[Scaffolder] Le projet n'est pas initialisé correctement."
            ]
        }

    if not src_dir.exists():
        return {
            "logs": [
                f"[Scaffolder] ❌ Dossier src introuvable dans {project_dir}.",
                "[Scaffolder] Le projet Vite semble incomplet."
            ]
        }

    logs.append(f"[Scaffolder] Projet existant détecté : {project_dir}")

    # ✅ On garde juste la config Tailwind si besoin
    if vite_config.exists():
        with open(vite_config, "r", encoding="utf-8") as f:
            vite_content = f.read()

        if "tailwindcss" not in vite_content:
            vite_content = vite_content.replace(
                "import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'",
                "import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'\nimport tailwindcss from '@tailwindcss/vite'"
            ).replace(
                "plugins: [react()]",
                "plugins: [react(), tailwindcss()]"
            )

            with open(vite_config, "w", encoding="utf-8") as f:
                f.write(vite_content)

            logs.append("[Scaffolder] vite.config.js mis à jour pour Tailwind.")
    else:
        logs.append("[Scaffolder] ⚠️ vite.config.js introuvable, aucune mise à jour faite.")

    # ✅ index.css (Uniquement Tailwind, les polices sont gérées dans le HTML)
    css_path = project_dir / "src" / "index.css"
    css_path.parent.mkdir(parents=True, exist_ok=True)
    with open(css_path, "w", encoding="utf-8") as f:
        f.write('@import "tailwindcss";\n')

    logs.append("[Scaffolder] index.css configuré pour Tailwind.")

    # ✅ Création arborescence planning
    print("[📁 Scaffolder] Création de l'arborescence...")
    for folder in planning.get("folders", []):
        (project_dir / folder["path"]).mkdir(parents=True, exist_ok=True)

    assets_path = project_dir / "src" / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (assets_path / ".gitkeep").touch()

    for file_info in planning.get("files", []):
        file_path = project_dir / file_info["path"]
        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"// TODO: Implémenter {file_info.get('component_name', 'Ce composant')}\n")

    logs.append("[Scaffolder] Arborescence créée (dont src/assets).")

    # ✅ Génération App.jsx
    _generate_app_router(planning, project_dir)

    # ✅ NOUVEAU : Injection automatique des polices dans index.html
    _inject_google_fonts(project_dir)

    # ✅ Nettoyage fichiers inutiles Vite
    (project_dir / "src" / "App.css").unlink(missing_ok=True)
    (project_dir / "src" / "assets" / "react.svg").unlink(missing_ok=True)
    (project_dir / "public" / "vite.svg").unlink(missing_ok=True)

    logs.append("[Scaffolder] Fichiers par défaut de Vite nettoyés.")

    print(f"[✅ Scaffolder] Projet prêt à coder dans {project_dir}\n")

    return {
        "generated_project_path": str(project_dir),
        "logs": logs
    }