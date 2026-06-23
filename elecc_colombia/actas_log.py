from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

from elecc_colombia.config import INTERIM_DATA_DIR

LOG_COLUMNS = ["RETRIEVAL_TIMESTAMP", "DEPARTAMENTO", "MUNICIPIO", "ZONA", "PUESTO", "MESA", "ACTA_PDF"]
ACTAS_LOG_PATH = INTERIM_DATA_DIR / "actas_log.csv"


def save_actas_log(
    records: list[dict],
    path: Path = ACTAS_LOG_PATH,
    overwrite: bool = False,
) -> None:
    """Write records to the actas log CSV.

    Args:
        records:   List of dicts with keys DEPARTAMENTO, MUNICIPIO, ZONA, PUESTO, MESA, ACTA_PDF.
        path:      Destination CSV file.
        overwrite: If True, replace the file; if False (default), append to it.
    """
    if not records:
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    df = pd.DataFrame(records)
    df.insert(0, "RETRIEVAL_TIMESTAMP", timestamp)
    df = df.reindex(columns=LOG_COLUMNS)

    if overwrite:
        df.to_csv(path, mode="w", index=False)
        logger.info(f"Overwrote {path} with {len(records)} records")
    else:
        write_header = not path.exists()
        df.to_csv(path, mode="a", index=False, header=write_header)
        logger.info(f"Appended {len(records)} records to {path}")


def load_actas_log(path: Path = ACTAS_LOG_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def load_downloaded_paths(
    departamento: str,
    path: Path = ACTAS_LOG_PATH,
) -> set[str]:
    """Return the set of ACTA_PDF paths already logged for a given departamento.

    Used by download_all_actas to skip mesas that are already recorded in the
    log, preventing duplicate downloads and duplicate log entries on resume.

    Returns an empty set if the log file does not exist or has no rows for
    that departamento.
    """
    if not path.exists():
        return set()
    df = pd.read_csv(path, usecols=["DEPARTAMENTO", "ACTA_PDF"])
    mask = df["DEPARTAMENTO"].str.strip().str.upper() == departamento.strip().upper()
    return set(df.loc[mask, "ACTA_PDF"].dropna().astype(str))
