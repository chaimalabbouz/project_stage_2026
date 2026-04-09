import re
import subprocess
from pathlib import Path

from agents.codegen_agent.agent import build_codegen_llm

PROJECT_DIR = Path("data/generated_projects/fintech_landing")
MAX_ATTEMPTS = 3


def run_build() -> tuple[bool, str]:
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return result.returncode == 0, output


def extract_error_files(build_output: str) -> list[str]:
    """
    Extrait uniquement les vrais chemins de fichiers JSX/JS dans les erreurs.
    Évite les faux chemins du style:
    src/sections/Hero' in src/pages/Frontpage.jsx
    """
    patterns = [
        r"(src/[A-Za-z0-9_\-./]+\.jsx)",
        r"(src/[A-Za-z0-9_\-./]+\.js)",
    ]

    found = []
    for pattern in patterns:
        found.extend(re.findall(pattern, build_output))

    cleaned = []
    for item in found:
        item = item.strip()
        item = item.rstrip("',.;:)")
        if item not in cleaned:
            cleaned.append(item)

    return cleaned


def build_fix_prompt(file_path: str, file_content: str, build_output: str) -> str:
    return f"""
You are a React JSX debugging expert.

Fix the following file so that the project compiles successfully.

STRICT RULES:
1. Return ONLY the corrected file content.
2. Do NOT use markdown fences.
3. Do NOT explain anything.
4. Keep the component name and overall structure when possible.
5. Fix JSX syntax errors, missing closing tags, invalid imports, invalid exports, broken strings, and obvious React syntax issues.
6. If an import path is clearly wrong, fix it.
7. Do not rewrite the entire architecture unless necessary.
8. Preserve Tailwind classes when possible.

TARGET FILE:
{file_path}

CURRENT FILE CONTENT:
{file_content}

FULL BUILD ERRORS:
{build_output}
""".strip()


def fix_file_with_llm(file_path: str, build_output: str):
    llm = build_codegen_llm()

    full_path = PROJECT_DIR / file_path
    if not full_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {full_path}")

    current_code = full_path.read_text(encoding="utf-8")
    prompt = build_fix_prompt(file_path, current_code, build_output)

    response = llm.invoke([{"role": "user", "content": prompt}])
    fixed_code = response.content.strip()

    fixed_code = (
        fixed_code.replace("```jsx", "")
        .replace("```javascript", "")
        .replace("```js", "")
        .replace("```", "")
        .strip()
    )

    full_path.write_text(fixed_code, encoding="utf-8")


def validation_node(state: dict) -> dict:
    logs = list(state.get("logs", []))

    for round_idx in range(MAX_ATTEMPTS):
        print(f"[Validation] Round {round_idx + 1}")

        ok, output = run_build()

        if ok:
            print("[Validation] Build OK")
            logs.append("[Validation] Build OK")
            return {
                "logs": logs,
                "build_output": output,
                "validation_success": True,
            }

        print("[Validation] Build FAILED")
        logs.append("[Validation] Build FAILED")

        error_files = extract_error_files(output)

        if not error_files:
            logs.append("[Validation] Aucun fichier JSX/JS identifié dans les erreurs.")
            return {
                "logs": logs,
                "build_output": output,
                "validation_success": False,
            }

        for file_path in error_files:
            try:
                print(f"[Validation] Correction de {file_path}")
                fix_file_with_llm(file_path, output)
                logs.append(f"[Validation] Fichier corrigé: {file_path}")
            except Exception as e:
                print(f"[Validation] ERREUR sur {file_path}: {e}")
                logs.append(f"[Validation] ERREUR sur {file_path}: {e}")

    ok, output = run_build()
    if ok:
        logs.append("[Validation] Build OK après corrections.")
    else:
        logs.append("[Validation] Build toujours en échec après corrections.")

    return {
        "logs": logs,
        "build_output": output,
        "validation_success": ok,
    }