import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

FIGMA_API_KEY = os.getenv("FIGMA_API_KEY", "")
FIGMA_FILE_ID = os.getenv("FIGMA_FILE_ID", "")

RAW_OUTPUT_FILE = BASE_DIR / "data" / "raw" / "figma_raw.json"
CLEANED_OUTPUT_FILE = BASE_DIR / "data" / "processed" / "figma_cleaned.json"
COMPONENT_REU_OUTPUT_FILE = BASE_DIR / "data" / "component-reu" / "reusable_components.json"

PLANNER_DIR = BASE_DIR / "data" / "planner"
PLANNER_PAYLOAD_FILE = PLANNER_DIR / "planner_payload.json"
PLANNER_SUMMARY_FILE = PLANNER_DIR / "planner_summary.json"
PLANNER_CHUNKS_FILE = PLANNER_DIR / "planner_chunks.json"
PLANNER_PLANNING_FILE = PLANNER_DIR / "planning.json"   # <--- LA LIGNE QUI MANQUAIT

PLANNER_MAX_DEPTH = int(os.getenv("PLANNER_MAX_DEPTH", "3"))
PLANNER_MAX_CHARS_SINGLE_CALL = int(os.getenv("PLANNER_MAX_CHARS_SINGLE_CALL", "45000"))
PLANNER_MAX_CHARS_PER_CHUNK = int(os.getenv("PLANNER_MAX_CHARS_PER_CHUNK", "18000"))
PLANNER_MAX_CHUNKS = int(os.getenv("PLANNER_MAX_CHUNKS", "5"))

if not FIGMA_API_KEY:
    raise ValueError("FIGMA_API_KEY est manquant dans le fichier .env")

if not FIGMA_FILE_ID:
    raise ValueError("FIGMA_FILE_ID est manquant dans le fichier .env")