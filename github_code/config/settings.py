from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
FIGMA_API_KEY = os.getenv("FIGMA_API_KEY", "")
FIGMA_FILE_KEY = os.getenv("FIGMA_FILE_ID", "")


MODEL ="llama-3.3-70b-versatile"
CODESTRAL_MODEL = "codestral-latest"


# Inputs existants
RAW_OUTPUT_FILE = BASE_DIR / "data" / "raw" / "figma_raw.json"
MINIMAL_OUTPUT_FILE = BASE_DIR / "data" / "processed" / "figma_cleaned.json"

# Data isolée du sous-projet
DATA2_DIR = BASE_DIR / "data2"

TREE_OUTPUT_FILE = DATA2_DIR / "extracted" / "tree_3levels.json"
#REUSABLE_OUTPUT_FILE = DATA2_DIR / "extracted" / "reusable_components.json"
#voici la nouvelle
COMPONENT_REU_OUTPUT_FILE = DATA2_DIR / "extracted" / "components_reu.json"
SECTIONS_OUTPUT_FILE = DATA2_DIR / "extracted" / "sections.json"

INPUT_PLANNER_FILE = DATA2_DIR / "input_planner" / "payload.json"

ANALYSE_OUTPUT_FILE = DATA2_DIR / "plans" / "analyse.json"
ARCHITECTURE_FILE = DATA2_DIR / "plans" / "architecture.json"

OUTPUT_DIR = DATA2_DIR / "output"
PROJECT_NAME = "my-app"
PROJECT_DIR = OUTPUT_DIR / PROJECT_NAME
COMPONENTS_DIR = PROJECT_DIR / "src" / "components"
PAGES_DIR = PROJECT_DIR / "src" / "pages"

ASSETS_DIR = PROJECT_DIR / "src" / "assets"
ICONS_OUTPUT_FILE = DATA2_DIR / "extracted" / "icons.json"
