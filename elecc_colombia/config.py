from pathlib import Path
import os
import sys
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file if it exists
load_dotenv()

# Paths
PROJ_ROOT = Path(__file__).resolve().parents[1]
logger.info(f"PROJ_ROOT path is: {PROJ_ROOT}")

DATA_DIR = PROJ_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"

MODELS_DIR = PROJ_ROOT / "models"

REPORTS_DIR = PROJ_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

# ── Scraper ────────────────────────────────────────────────────────────────────
DEPARTMENT_ID = 72
HEADLESS = False
SLOW_MO = 400

# The URL template for the scraper, which will be formatted with the DEPARTMENT_ID
BASE_URL = f"https://divulgacione14presidente.registraduria.gov.co/departamento/"
READY_SELECTOR = "input[placeholder='seleccione el municipio']"

def setup_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()  # default to INFO if not set

    logger.remove()  # remove default handler
    logger.add(
        sink=sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - {message}",
        colorize=True,
    )

    # Optional: also log to file in production
    if log_level != "DEBUG":
        logger.add(
            "logs/app.log",
            level=log_level,
            rotation="10 MB",
            retention="7 days",
        )
    
    return logger

# If tqdm is installed, configure loguru with tqdm.write
# https://github.com/Delgan/loguru/issues/135
try:
    from tqdm import tqdm

    logger.remove(0)
    logger.add(lambda msg: tqdm.write(msg, end=""), colorize=True)
except ModuleNotFoundError:
    pass
