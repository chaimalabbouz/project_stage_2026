"""
val.py
======
Validateur AGENT du projet React généré.

Fonctionne en BOUCLE jusqu'à compilation réussie ou max itérations :

  1. Phase 0 — Renommage des fichiers à noms invalides (une seule fois)
  2. Phase 1 — Nettoyage déterministe de TOUS les fichiers (une seule fois)
  3. BOUCLE AGENT (max MAX_ITERATIONS tours) :
     a. Compiler (tsc --noEmit)
     b. Vérifier la cohérence inter-fichiers (imports, props)
     c. Si 0 erreurs → SUCCÈS, on arrête
     d. Sinon → Trier les fichiers par nombre d'erreurs (décroissant)
     e. Pour chaque fichier avec erreurs :
        - Lire le fichier + les erreurs + le contexte des voisins
        - Appeler le LLM correcteur
        - Écrire le fichier corrigé
        - Nettoyer (data-fname, markdown, <think>)
     f. Retour en (a)

Modèle : Qwen3-32B sur Groq (mode non-thinking).
"""

import json
import re
import subprocess
import time
from pathlib import Path
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_API_KEY, OUTPUT_DIR, ARCHITECTURE_FILE


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

PROJECT_DIR = OUTPUT_DIR / "my-app"
SRC_DIR = PROJECT_DIR / "src"
COMPONENTS_DIR = SRC_DIR / "components"
PAGES_DIR = SRC_DIR / "pages"
VALIDATOR_MODEL = "llama-3.3-70b-versatile"
LLM_DELAY =15
MAX_LLM_RETRIES = 5
MAX_ITERATIONS = 15          # Nombre max de tours de boucle agent
MAX_FILES_PER_ITERATION = 3  # Fichiers corrigés par tour (évite rate limit)

NO_THINK_SUFFIX = "\n\n/no_think"


# ═══════════════════════════════════════════════════════════════
# PROMPT LLM CORRECTEUR
# ═══════════════════════════════════════════════════════════════

FIX_SYSTEM_PROMPT = ("""
Tu es un expert React TypeScript qui CORRIGE du code cassé.

Tu reçois :
- Le contenu COMPLET d un fichier .tsx qui a des erreurs
- La liste EXACTE des erreurs (TypeScript + incohérences d imports/props)
- Le contexte des composants voisins (leurs interfaces Props + exports)

Tu dois retourner le fichier .tsx COMPLET et CORRIGÉ.
Pas de markdown, pas de texte avant/après, pas de commentaires sur ton travail.
Juste le code TypeScript corrigé, rien d autre.

RÈGLES STRICTES — LIS ATTENTIVEMENT :

1. STRUCTURE : NE CHANGE PAS la structure JSX ni la logique du composant.
   Tu corriges UNIQUEMENT ce qui est signalé dans les erreurs.

2. PROPS : NE RENOMME JAMAIS les props existantes.
   - Si une prop est utilisée dans le JSX mais absente de l interface Props :
     AJOUTE-la à l interface avec le type approprié (string par défaut).
   - Si une prop est dans l interface mais pas utilisée : GARDE-la quand même.

3. IMPORTS :
   - Si un import pointe vers un fichier qui n existe pas : CORRIGE le chemin.
   - Si le nom importé ne correspond pas au export default du fichier cible :
     RENOMME l import pour correspondre au export du fichier cible.
     Exemple : le fichier TabComponent.tsx exporte "TabComponent" mais tu
     importes "Tab" → change en "import TabComponent from './TabComponent'"
     ET remplace tous les usages <Tab .../> par <TabComponent .../>.
   - Si un import manque complètement : AJOUTE-le.

4. TYPES :
   - Corrige les erreurs de types TypeScript signalées.
   - Si un composant est utilisé avec des props qu il n accepte pas,
     AJOUTE les props à l interface du composant cible SI c est le fichier
     en cours de correction. Sinon, note-le comme commentaire.

5. NETTOYAGE :
   - Retire tout data-fname="..." oublié.
   - Retire tout bloc <think>...</think>.
   - Retire les commentaires parasites du LLM.
   - Assure-toi qu il y a UN SEUL export default.

6. IMPORTS REACT :
   - Si le fichier utilise JSX, assure import React from 'react' en haut.
   - Si le fichier utilise clsx(), assure import clsx from 'clsx' en haut.

7. LE CODE RETOURNÉ DOIT COMPILER SANS ERREUR TypeScript.
""".strip() + NO_THINK_SUFFIX)


# ═══════════════════════════════════════════════════════════════
# TOOL : Appel LLM
# ═══════════════════════════════════════════════════════════════

def tool_call_llm(llm: ChatGroq, system_prompt: str, user_content: str,
                  max_tokens: int = 4096) -> str:
    """Appel LLM avec retry sur rate-limit et nettoyage automatique."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    for attempt in range(MAX_LLM_RETRIES):
        try:
            response = llm.invoke(messages, max_tokens=max_tokens)
            raw = response.content.strip()

            # Retirer les blocs <think>...</think>
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            # Retirer les fences markdown
            if raw.startswith("```"):
                lines = raw.split("\n")
                end_idx = len(lines) - 1
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip().startswith("```"):
                        end_idx = i
                        break
                raw = "\n".join(lines[1:end_idx]).strip()

            time.sleep(LLM_DELAY)
            return raw
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = (attempt + 1) * 6
                print(f"    [RATE LIMIT] Attente {wait}s ({attempt+1}/{MAX_LLM_RETRIES})...")
                time.sleep(wait)
            else:
                raise e
    raise RuntimeError("Rate limit : max retries atteint")


# ═══════════════════════════════════════════════════════════════
# TOOL : Lire / Écrire fichiers
# ═══════════════════════════════════════════════════════════════

def tool_read_file(path: Path) -> str | None:
    """Lit un fichier .tsx. Retourne None si erreur."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"    [ERREUR] Lecture {path.name} : {e}")
        return None


def tool_write_file(path: Path, content: str) -> bool:
    """Écrit un fichier .tsx. Retourne True si succès."""
    try:
        path.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"    [ERREUR] Écriture {path.name} : {e}")
        return False


def tool_list_tsx_files() -> list[Path]:
    """Liste tous les .tsx du projet."""
    files = []
    if COMPONENTS_DIR.exists():
        files.extend(COMPONENTS_DIR.glob("*.tsx"))
    if PAGES_DIR.exists():
        files.extend(PAGES_DIR.glob("*.tsx"))
    return sorted(files)


# ═══════════════════════════════════════════════════════════════
# TOOL : Compilation TSC
# ═══════════════════════════════════════════════════════════════

def tool_compile() -> dict[str, list[dict]]:
    """Lance tsc --noEmit et retourne les erreurs groupées par fichier absolu.
    Retourne {} si pas de tsconfig ou pas d erreurs."""
    tsconfig = PROJECT_DIR / "tsconfig.json"
    if not tsconfig.exists():
        print("  [TSC] Pas de tsconfig.json → compilation sautée")
        return {}

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--pretty", "false"],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("  [TSC] npx/tsc non trouvé → compilation sautée")
        return {}
    except subprocess.TimeoutExpired:
        print("  [TSC] Timeout → compilation sautée")
        return {}

    output = (result.stdout or "") + "\n" + (result.stderr or "")

    errors_by_file: dict[str, list[dict]] = {}
    for line in output.split("\n"):
        m = re.match(
            r"^(.*?\.tsx?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.*)$",
            line.strip()
        )
        if m:
            rel_file = m.group(1)
            abs_file = str((PROJECT_DIR / rel_file).resolve())
            errors_by_file.setdefault(abs_file, []).append({
                "file": rel_file,
                "line": int(m.group(2)),
                "col": int(m.group(3)),
                "code": m.group(4),
                "message": m.group(5),
            })

    return errors_by_file


# ═══════════════════════════════════════════════════════════════
# TOOL : Cohérence inter-fichiers
# ═══════════════════════════════════════════════════════════════

def _extract_export_default_name(code: str) -> str | None:
    """Retrouve le nom du export default."""
    m = re.search(r"^export\s+default\s+function\s+([A-Za-z_]\w*)", code, re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(r"export\s+default\s+([A-Za-z_]\w*)\s*;", code)
    if m:
        return m.group(1)
    # const X = ...; export default X;
    m = re.search(r"export\s+default\s+([A-Za-z_]\w*)", code)
    if m:
        return m.group(1)
    return None


def _extract_props_interface(code: str) -> set[str]:
    """Retourne l'ensemble des noms de props dans l'interface Props."""
    m = re.search(r"(?:interface|type)\s+\w+Props\s*[={]\s*\{([^}]*)\}", code, re.DOTALL)
    if not m:
        return set()
    body = m.group(1)
    return {pm.group(1) for pm in re.finditer(r"([A-Za-z_]\w*)\s*\??\s*:", body)}


def _extract_local_imports(code: str) -> list[dict]:
    """Extrait les imports locaux (chemins relatifs)."""
    imports = []
    for m in re.finditer(
        r"^import\s+(?:(\w+)|\{([^}]+)\})\s+from\s+['\"](\.[^'\"]+)['\"]",
        code, re.MULTILINE,
    ):
        default_name = m.group(1)
        named = m.group(2)
        path = m.group(3)
        if default_name:
            imports.append({"type": "default", "name": default_name, "path": path})
        elif named:
            for n in named.split(","):
                clean = n.strip()
                if clean:
                    imports.append({"type": "named", "name": clean, "path": path})
    return imports


def _extract_jsx_usage_props(code: str, component_name: str) -> set[str]:
    """Cherche les props passées à <ComponentName ... /> dans le code."""
    props = set()
    pattern = r"<" + re.escape(component_name) + r"\s+([^>]*?)(?:/\s*>|>)"
    for m in re.finditer(pattern, code, re.DOTALL):
        for am in re.finditer(r"([A-Za-z_]\w*)\s*=", m.group(1)):
            props.add(am.group(1))
    return props


def tool_check_coherence() -> dict[str, list[dict]]:
    """Vérifie la cohérence des imports/exports/props entre fichiers.
    Retourne {abs_file_path: [erreurs]}."""
    tsx_files = tool_list_tsx_files()

    # Index par fichier
    index = {}
    for path in tsx_files:
        content = tool_read_file(path)
        if content is None:
            continue
        index[str(path.resolve())] = {
            "path": path,
            "content": content,
            "export_name": _extract_export_default_name(content),
            "props_declared": _extract_props_interface(content),
        }

    # Index par basename (sans extension)
    by_basename = {}
    for abs_path, info in index.items():
        by_basename[Path(abs_path).stem] = info

    errors: dict[str, list[dict]] = {}

    for abs_path, info in index.items():
        file_errors = []
        imports = _extract_local_imports(info["content"])

        for imp in imports:
            if imp["type"] != "default":
                continue

            imp_basename = Path(imp["path"]).stem
            target = by_basename.get(imp_basename)

            if not target:
                file_errors.append({
                    "kind": "missing_import_target",
                    "message": (
                        f"Import '{imp['name']}' from '{imp['path']}' : "
                        f"fichier '{imp_basename}.tsx' introuvable."
                    ),
                })
                continue

            # Vérifier nom import vs export
            target_export = target["export_name"]
            if target_export and imp["name"] != target_export:
                file_errors.append({
                    "kind": "import_export_mismatch",
                    "message": (
                        f"Import '{imp['name']}' mais '{imp_basename}.tsx' "
                        f"exporte '{target_export}'. "
                        f"Renommer l'import en '{target_export}' et remplacer "
                        f"tous les usages <{imp['name']} .../> par <{target_export} .../>."
                    ),
                    "target_file": str(target["path"].resolve()),
                })

            # Vérifier props passées vs props déclarées
            props_passed = _extract_jsx_usage_props(info["content"], imp["name"])
            if target["props_declared"]:
                unknown = props_passed - target["props_declared"]
                for prop in unknown:
                    file_errors.append({
                        "kind": "unknown_prop",
                        "message": (
                            f"<{imp['name']}> reçoit la prop '{prop}' qui "
                            f"n'existe pas dans l'interface Props de "
                            f"'{imp_basename}.tsx'. "
                            f"AJOUTER '{prop}?: string;' à l'interface Props "
                            f"de '{imp_basename}.tsx'."
                        ),
                        "target_file": str(target["path"].resolve()),
                    })

        if file_errors:
            errors[abs_path] = file_errors

    return errors


# ═══════════════════════════════════════════════════════════════
# TOOL : Corriger un fichier via LLM
# ═══════════════════════════════════════════════════════════════

def _build_error_description(errors: list[dict]) -> str:
    """Formate les erreurs en texte lisible pour le LLM."""
    lines = []
    for i, err in enumerate(errors, 1):
        if "line" in err:
            lines.append(
                f"{i}. Ligne {err['line']}, col {err['col']} "
                f"(TSC {err['code']}): {err['message']}"
            )
        else:
            lines.append(f"{i}. [{err['kind']}]: {err['message']}")
    return "\n".join(lines)


def _build_neighbor_context(
    target_abs: str,
    errors: list[dict],
    all_files: dict[str, str],
) -> str:
    """Construit le contexte des fichiers voisins référencés dans les erreurs."""
    referenced = set()
    for err in errors:
        tf = err.get("target_file")
        if tf and tf != target_abs:
            referenced.add(tf)

    if not referenced:
        return ""

    parts = []
    for ref_path in referenced:
        content = all_files.get(ref_path)
        if not content:
            continue

        file_name = Path(ref_path).name

        # Extraire interface Props
        interface_match = re.search(
            r"((?:interface|type)\s+\w+Props\s*[={]\s*\{[^}]*\})",
            content, re.DOTALL,
        )
        # Extraire signature export
        export_match = re.search(
            r"(export\s+default\s+function\s+\w+\s*\([^)]*\))",
            content,
        )

        snippets = []
        if interface_match:
            snippets.append(interface_match.group(1))
        if export_match:
            snippets.append(export_match.group(1))

        if snippets:
            parts.append(f"// ─── {file_name} ───\n" + "\n".join(snippets))

    if not parts:
        return ""

    return "\n\nContexte des composants voisins :\n" + "\n\n".join(parts)


def tool_fix_file(
    path: Path,
    errors: list[dict],
    all_files: dict[str, str],
    llm: ChatGroq,
) -> bool:
    """Corrige un fichier via LLM. Retourne True si modifié."""
    content = tool_read_file(path)
    if content is None:
        return False

    # Ne pas corriger les stubs
    non_empty = [l for l in content.split("\n") if l.strip()]
    if len(non_empty) <= 3 and "export" not in content:
        print(f"    [SKIP] {path.name} : fichier stub")
        return False

    abs_path = str(path.resolve())
    error_desc = _build_error_description(errors)
    context = _build_neighbor_context(abs_path, errors, all_files)

    user_content = (
        f"Fichier : {path.name}\n\n"
        f"Code actuel :\n{content}\n\n"
        f"Erreurs à corriger :\n{error_desc}"
        f"{context}\n\n"
        f"Retourne le fichier COMPLET corrigé."
    )

    try:
        fixed = tool_call_llm(llm, FIX_SYSTEM_PROMPT, user_content)
        fixed = _deterministic_cleanup(fixed)

        if fixed and fixed.strip() != content.strip():
            tool_write_file(path, fixed)
            return True
        else:
            print(f"    [NOOP] {path.name} : pas de changement")
            return False
    except Exception as e:
        print(f"    [ERREUR] LLM pour {path.name} : {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# Nettoyage déterministe (appliqué après chaque correction LLM)
# ═══════════════════════════════════════════════════════════════

def _deterministic_cleanup(code: str) -> str:
    """Nettoyage déterministe complet d'un fichier .tsx."""

    # 1. Retirer <think>...</think> (Qwen3 reasoning)
    code = re.sub(r'<think>.*?</think>', '', code, flags=re.DOTALL | re.IGNORECASE)
    # Si </think> manque (tronqué) : retirer depuis <think> jusqu'au premier mot-clé
    code = re.sub(
        r'<think>.*?(?=(?:import |export |interface |function |const ))',
        '', code, flags=re.DOTALL | re.IGNORECASE
    )

    # 2. Retirer fences markdown
    code = re.sub(r'^```(?:tsx|typescript|ts|jsx|javascript|js)?\s*\n', '', code)
    code = re.sub(r'\n```\s*$', '', code)
    code = re.sub(r'\n```\s*\n', '\n', code)

    # 3. Retirer data-fname
    code = re.sub(r'\s+data-fname="[^"]*"', '', code)
    code = re.sub(r"\s+data-fname='[^']*'", '', code)
    code = re.sub(r'\s+data-fname=\{[^}]*\}', '', code)

    # 4. Retirer data-variant-*
    code = re.sub(r'\s+data-variant-[a-zA-Z]+=\{[^}]*\}', '', code)

    # 5. Retirer lignes parasites du LLM
    parasitic = [
        r"^\s*//\s*(génération|generation|généré|generated|termine|terminé|"
        r"terminée|finished|done|end|fin\b|fini)\b.*$",
        r"^\s*//\s*(voici|here (is|are)|je vais|let me|i will|now i).*$",
        r"^\s*\{\s*/\*\s*(génération|generation|fin|end|généré|generated).*\*/\s*\}\s*$",
    ]
    lines = code.split("\n")
    cleaned_lines = []
    for line in lines:
        skip = False
        for p in parasitic:
            if re.match(p, line, re.IGNORECASE):
                skip = True
                break
        if not skip:
            cleaned_lines.append(line)
    code = "\n".join(cleaned_lines)

    # 6. Dédupliquer export default
    matches = list(re.finditer(r"^export\s+default\s+", code, re.MULTILINE))
    if len(matches) > 1:
        for m in reversed(matches[:-1]):
            start = m.start()
            end_nl = code.find("\n", start)
            if end_nl == -1:
                end_nl = len(code)
            code = code[:start] + code[end_nl + 1:]

    # 7. Réduire les lignes vides consécutives
    code = re.sub(r"\n{3,}", "\n\n", code)

    return code.strip() + "\n"


# ═══════════════════════════════════════════════════════════════
# Phase 0 — Renommage des fichiers à noms invalides
# ═══════════════════════════════════════════════════════════════

def _to_pascal_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[0].upper() + p[1:] for p in parts if p)


def phase0_rename_files() -> int:
    """Renomme les fichiers avec noms invalides et met à jour les imports."""
    print("\n[val] PHASE 0 — Renommage fichiers invalides")

    to_rename: dict[Path, Path] = {}
    for directory in (COMPONENTS_DIR, PAGES_DIR):
        if not directory.exists():
            continue
        for path in directory.glob("*.tsx"):
            stem = path.stem
            if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", stem):
                new_stem = _to_pascal_case(stem)
                if new_stem and new_stem != stem:
                    new_path = path.parent / f"{new_stem}.tsx"
                    if not new_path.exists():
                        to_rename[path] = new_path

    if not to_rename:
        print("  Aucun fichier à renommer.")
        return 0

    renamed = 0
    for old_path, new_path in to_rename.items():
        try:
            print(f"  [RENAME] {old_path.name} → {new_path.name}")
            old_path.rename(new_path)
            renamed += 1
        except Exception as e:
            print(f"  [ERREUR] {old_path.name} : {e}")

    # Mettre à jour les imports dans tous les .tsx
    if renamed > 0:
        all_tsx = tool_list_tsx_files()
        for path in all_tsx:
            try:
                content = path.read_text(encoding="utf-8")
                original = content
                for old_path, new_path in to_rename.items():
                    escaped = re.escape(old_path.stem)
                    content = re.sub(
                        r"(from\s+['\"][^'\"]*?/)" + escaped + r"(['\"])",
                        r"\g<1>" + new_path.stem + r"\2",
                        content,
                    )
                    # Mettre à jour les usages JSX si le nom de composant a changé
                    old_pascal = _to_pascal_case(old_path.stem)
                    new_pascal = new_path.stem
                    if old_pascal != new_pascal:
                        content = re.sub(
                            r"<" + re.escape(old_pascal) + r"(\s|/|>)",
                            f"<{new_pascal}\\1",
                            content,
                        )
                        content = re.sub(
                            r"</" + re.escape(old_pascal) + r">",
                            f"</{new_pascal}>",
                            content,
                        )
                if content != original:
                    path.write_text(content, encoding="utf-8")
                    print(f"  [IMPORT] {path.name} : imports mis à jour")
            except Exception:
                pass

    print(f"  {renamed} fichier(s) renommé(s)")
    return renamed


# ═══════════════════════════════════════════════════════════════
# Phase 1 — Nettoyage déterministe initial
# ═══════════════════════════════════════════════════════════════

def phase1_cleanup_all() -> int:
    """Applique le nettoyage déterministe à tous les .tsx."""
    print("\n[val] PHASE 1 — Nettoyage déterministe")

    tsx_files = tool_list_tsx_files()
    modified = 0

    for path in tsx_files:
        content = tool_read_file(path)
        if content is None:
            continue
        cleaned = _deterministic_cleanup(content)
        if cleaned != content:
            tool_write_file(path, cleaned)
            modified += 1
            print(f"  [CLEAN] {path.name}")

    print(f"  {modified}/{len(tsx_files)} fichiers nettoyés")
    return modified


# ═══════════════════════════════════════════════════════════════
# BOUCLE AGENT PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def _merge_errors(
    tsc: dict[str, list[dict]],
    coherence: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Fusionne les erreurs TSC et de cohérence par fichier."""
    merged: dict[str, list[dict]] = {}
    for f, errs in tsc.items():
        merged.setdefault(f, []).extend(errs)
    for f, errs in coherence.items():
        merged.setdefault(f, []).extend(errs)
    return merged


def _load_all_files_content() -> dict[str, str]:
    """Charge le contenu de tous les .tsx en mémoire."""
    contents = {}
    for path in tool_list_tsx_files():
        content = tool_read_file(path)
        if content:
            contents[str(path.resolve())] = content
    return contents


def agent_loop(llm: ChatGroq) -> dict:
    """Boucle agent : compile → analyse → corrige → répète.
    Retourne le rapport final."""

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'─' * 50}")
        print(f"  ITÉRATION {iteration}/{MAX_ITERATIONS}")
        print(f"{'─' * 50}")

        # ─── Étape A : Compiler ───
        print("\n  [A] Compilation TSC...")
        tsc_errors = tool_compile()
        n_tsc = sum(len(e) for e in tsc_errors.values())
        print(f"      {n_tsc} erreurs TSC")

        # ─── Étape B : Cohérence ───
        print("\n  [B] Vérification cohérence...")
        coherence_errors = tool_check_coherence()
        n_coh = sum(len(e) for e in coherence_errors.values())
        print(f"      {n_coh} incohérences")

        # ─── Étape C : Fusionner et vérifier ───
        all_errors = _merge_errors(tsc_errors, coherence_errors)
        total = sum(len(e) for e in all_errors.values())

        if total == 0:
            print("\n  ✓ AUCUNE ERREUR — compilation réussie !")
            return {
                "status": "success",
                "iterations": iteration,
                "remaining_errors": 0,
            }

        print(f"\n      TOTAL : {total} erreur(s) dans {len(all_errors)} fichier(s)")

        # ─── Étape D : Trier les fichiers par criticité ───
        sorted_files = sorted(
            all_errors.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        # ─── Étape E : Corriger les fichiers les plus critiques ───
        all_contents = _load_all_files_content()
        corrected_this_round = 0

        for abs_file, errors in sorted_files[:MAX_FILES_PER_ITERATION]:
            path = Path(abs_file)
            if not path.exists():
                print(f"    [SKIP] {path.name} : fichier disparu")
                continue

            print(f"\n    [FIX] {path.name} ({len(errors)} erreur(s))...")
            success = tool_fix_file(path, errors, all_contents, llm)
            if success:
                corrected_this_round += 1
                print(f"    [OK]  {path.name} corrigé")
            else:
                print(f"    [---] {path.name} : pas de correction")

        if corrected_this_round == 0:
            print("\n  ⚠ Aucune correction effectuée ce tour — arrêt pour éviter boucle infinie")
            return {
                "status": "stuck",
                "iterations": iteration,
                "remaining_errors": total,
            }

        print(f"\n  → {corrected_this_round} fichier(s) corrigé(s) ce tour")

    # Max itérations atteint
    final_tsc = tool_compile()
    final_total = sum(len(e) for e in final_tsc.values())
    print(f"\n  ⚠ Max itérations atteint. {final_total} erreurs restantes.")

    return {
        "status": "max_iterations",
        "iterations": MAX_ITERATIONS,
        "remaining_errors": final_total,
    }


# ═══════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

def run_validateur() -> dict:
    """Lance le pipeline complet de validation."""
    print("\n" + "═" * 60)
    print("  VALIDATEUR AGENT — démarrage")
    print("═" * 60)

    if not PROJECT_DIR.exists():
        print(f"[val] Projet introuvable : {PROJECT_DIR}")
        return {"status": "no_project"}

    llm = ChatGroq(
        model=VALIDATOR_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0,
    )

    # ─── Phase 0 : renommage ───
    renamed = phase0_rename_files()

    # ─── Phase 1 : nettoyage déterministe ───
    cleaned = phase1_cleanup_all()

    # ─── Boucle agent ───
    report = agent_loop(llm)

    # ─── Rapport final ───
    print("\n" + "═" * 60)
    print("  RAPPORT FINAL")
    print("═" * 60)
    print(f"  Fichiers renommés      : {renamed}")
    print(f"  Fichiers nettoyés      : {cleaned}")
    print(f"  Itérations agent       : {report['iterations']}")
    print(f"  Statut                 : {report['status']}")
    print(f"  Erreurs restantes      : {report['remaining_errors']}")
    print("═" * 60)

    report["renamed"] = renamed
    report["cleaned"] = cleaned
    return report