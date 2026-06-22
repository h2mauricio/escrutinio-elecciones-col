import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import easyocr
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
from loguru import logger

from elecc_colombia.config import INTERIM_DATA_DIR


CROPS_DIR = INTERIM_DATA_DIR / "crops"

NIVELACION_LABELS = [
    "TOTAL VOTANTES FORMULARIO E-11",
    "TOTAL VOTOS EN LA URNA",
    "TOTAL VOTOS INCINERADOS",
]

CANDIDATOS_LABELS = [
    "IVÁN CEPEDA CASTRO",
    "ABELARDO DE LA ESPRIELLA",
]

TOTAL_VOTOS_LABELS = [
    "VOTOS EN BLANCO",
    "VOTOS NULOS",
    "VOTOS NO MARCADOS",
    "SUMA TOTAL",
]

ALL_HANDWRITTEN_LABELS = NIVELACION_LABELS + CANDIDATOS_LABELS + TOTAL_VOTOS_LABELS


@dataclass
class CropSpec:
    """Defines the crop window relative to a label row found by EasyOCR.

    All fractions are relative to full image dimensions so the same spec works
    regardless of scan resolution.

    Attributes:
        x_start_frac:  Left edge of crop as fraction of image width.
        x_end_frac:    Right edge of crop as fraction of image width.
        y_pad_frac:    Vertical padding above/below the label row as a multiple
                       of the row height.
        top_trim_frac: Fraction of padded crop height to remove from top
                       (trims the printed label text so only the handwritten
                       area remains).
    """
    x_start_frac: float = 0.67
    x_end_frac: float = 0.867
    y_pad_frac: float = 1.0
    top_trim_frac: float = 0.13


DEFAULT_CROP_SPEC = CropSpec()


def _label_to_slug(label: str) -> str:
    """Convert a label to an ASCII filename slug.

    'TOTAL VOTANTES FORMULARIO E-11' → 'TOTAL_VOTANTES_FORMULARIO_E_11'
    'IVÁN CEPEDA CASTRO'             → 'IVAN_CEPEDA_CASTRO'
    """
    normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^\w\s-]", "", normalized)
    return re.sub(r"[\s-]+", "_", clean.strip()).upper()


def _label_matches(detected: str, target: str, threshold: float = 0.6) -> bool:
    """True if enough words from target appear in detected (tolerates OCR noise)."""
    detected_upper = detected.upper()
    words = target.split()
    matched = sum(1 for w in words if w in detected_upper)
    return matched / len(words) >= threshold


def _apply_crop(img: np.ndarray, y_top: int, y_bottom: int, spec: CropSpec) -> np.ndarray:
    """Crop the handwritten region adjacent to a label row using the given CropSpec."""
    img_h, img_w = img.shape[:2]
    x_start = int(img_w * spec.x_start_frac)
    x_end = int(img_w * spec.x_end_frac)
    row_h = max(1, y_bottom - y_top)
    pad_y = max(10, int(row_h * spec.y_pad_frac))
    crop_top = max(0, y_top - pad_y)
    crop_bot = min(img_h, y_bottom + pad_y)
    top_trim = int((crop_bot - crop_top) * spec.top_trim_frac)
    return img[crop_top + top_trim : crop_bot, x_start:x_end]


def save_handwritten_crops(
    pdf_path: Path,
    labels: list[str] | None = None,
    crop_spec: CropSpec | dict[str, CropSpec] = DEFAULT_CROP_SPEC,
    crops_base_dir: Path = CROPS_DIR,
    dpi: int = 300,
) -> dict[str, Path | None]:
    """Find each label's row via EasyOCR and save the adjacent handwritten crop.

    Args:
        pdf_path:       Path to the acta PDF.
        labels:         Labels to look for (default: ALL_HANDWRITTEN_LABELS).
        crop_spec:      A single CropSpec applied to all labels, or a dict
                        mapping label → CropSpec for per-label coordinate tuning.
        crops_base_dir: Root directory for saved crops.
        dpi:            Resolution for PDF-to-image conversion.

    Crops are saved to:
        <crops_base_dir>/<departamento>/<pdf_stem>/<LABEL_SLUG>.png

    Returns:
        Dict mapping each label to its saved Path, or None if not found.
    """
    if labels is None:
        labels = ALL_HANDWRITTEN_LABELS

    images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
    img = np.array(images[0])

    # Save directory encodes departamento and full PDF metadata via the stem.
    crops_dir = crops_base_dir / pdf_path.parent.name / pdf_path.stem
    crops_dir.mkdir(parents=True, exist_ok=True)

    # Single EasyOCR pass — locate every label in one scan.
    easyocr_reader = easyocr.Reader(["es", "en"], gpu=False)
    label_rows: dict[str, tuple[int, int]] = {}
    for bbox, text, _ in easyocr_reader.readtext(img):
        for label in labels:
            if label not in label_rows and _label_matches(text, label):
                y_top = int(min(p[1] for p in bbox))
                y_bottom = int(max(p[1] for p in bbox))
                label_rows[label] = (y_top, y_bottom)
                logger.debug(f"Found '{label}' at y={y_top}–{y_bottom}")
                break

    # Crop and save each label region.
    saved: dict[str, Path | None] = {}
    for label in labels:
        if label not in label_rows:
            logger.warning(f"Label not found in '{pdf_path.name}': '{label}'")
            saved[label] = None
            continue

        spec = (
            crop_spec.get(label, DEFAULT_CROP_SPEC)
            if isinstance(crop_spec, dict)
            else crop_spec
        )
        y_top, y_bottom = label_rows[label]
        crop = _apply_crop(img, y_top, y_bottom, spec)

        save_path = crops_dir / f"{_label_to_slug(label)}.png"
        Image.fromarray(crop).save(save_path)
        logger.info(f"Saved crop: {save_path.relative_to(crops_base_dir.parent)}")
        saved[label] = save_path

    found = sum(1 for v in saved.values() if v is not None)
    logger.success(f"{pdf_path.name}: {found}/{len(labels)} crops saved → {crops_dir}")
    return saved


if __name__ == "__main__":
    import sys
    pdf = Path(sys.argv[1])
    results = save_handwritten_crops(pdf)
    for label, path in results.items():
        status = "✓" if path else "✗"
        print(f"  [{status}] {label}: {path}")
