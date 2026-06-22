from pathlib import Path
import os
import sys
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file if it exists
load_dotenv()

# Paths
PROJ_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJ_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"

MODELS_DIR = PROJ_ROOT / "models"

REPORTS_DIR = PROJ_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

# ── Scraper ────────────────────────────────────────────────────────────────────
HEADLESS = False
SLOW_MO = 400

#TODO: The URL will be read from a file instead of being hardcoded
# The URL template for the scraper, which will be formatted with the DEPARTMENT_ID
DEPARTMENT_ID = 60
BASE_URL = f"https://divulgacione14presidente.registraduria.gov.co/departamento/"

READY_SELECTOR = "input[placeholder='seleccione el municipio']"

LOGS_DIR = PROJ_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

def setup_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger.remove()
    logger.add(
        sink=sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - {message}",
        colorize=True,
    )
    logger.add(
        sink=LOGS_DIR / "run_{time:YYYY-MM-DD}.log",  # one file per day
        level="INFO",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} - {message}",
    )
    return logger


setup_logger()
