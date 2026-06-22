from pathlib import Path

import pandas as pd
from loguru import logger

from elecc_colombia.config import PROCESSED_DATA_DIR, PROJ_ROOT
from elecc_colombia.acta_text_reader import read_printed_info
from elecc_colombia.acta_handwrite_reader import save_handwritten_crops, CropSpec
from elecc_colombia.actas_log import ACTAS_LOG_PATH, load_actas_log

PROCESSED_LOG_PATH = PROCESSED_DATA_DIR / "actas_processed.csv"

_ACTA_COLUMNS = [
    # Location (matched later against website data)
    "DEPARTAMENTO_ACTA", "MUNICIPIO_ACTA", "ZONA_ACTA", "PUESTO_ACTA", "MESA_ACTA", "LUGAR_ACTA",
    # Election metadata
    "FECHA_ACTA", "TOTAL_PAGINAS",
    # Form tracking numbers
    "NM_FORM", "KIT", "CIV",
]


def process_acta(
    pdf_path: Path,
    crop_spec: CropSpec | dict[str, CropSpec] | None = None,
) -> dict:
    """Extract printed info and save handwritten crops for a single acta PDF.

    Args:
        pdf_path:  Path to the PDF.
        crop_spec: Override the default CropSpec for all labels, or pass a
                   per-label dict for fine-grained coordinate tuning.

    Returns a flat dict of all printed fields (_ACTA_COLUMNS).
    Handwritten crops are saved to data/interim/crops/ for ML training.
    """
    from elecc_colombia.acta_handwrite_reader import DEFAULT_CROP_SPEC
    printed = read_printed_info(pdf_path)
    save_handwritten_crops(pdf_path, crop_spec=crop_spec or DEFAULT_CROP_SPEC)
    return printed


def process_actas_log(
    log_path: Path = ACTAS_LOG_PATH,
    output_path: Path = PROCESSED_LOG_PATH,
    crop_spec: CropSpec | dict[str, CropSpec] | None = None,
) -> pd.DataFrame:
    """Process every PDF in the log: extract printed info, save handwritten crops,
    and write an enriched CSV to output_path."""
    df = load_actas_log(log_path)
    null_row = {col: None for col in _ACTA_COLUMNS}
    extra_rows = []

    for _, row in df.iterrows():
        pdf_path = PROJ_ROOT / row["ACTA_PDF"]
        if not pdf_path.exists():
            logger.warning(f"PDF not found, skipping: {pdf_path}")
            extra_rows.append(null_row.copy())
            continue
        try:
            extra_rows.append(process_acta(pdf_path, crop_spec=crop_spec))
            logger.success(f"Processed {pdf_path.name}")
        except Exception as e:
            logger.error(f"Failed {pdf_path.name}: {e}")
            extra_rows.append(null_row.copy())

    result_df = pd.concat([df, pd.DataFrame(extra_rows)], axis=1)
    result_df.to_csv(output_path, index=False)
    logger.success(f"Saved {len(result_df)} processed records to {output_path}")
    return result_df
