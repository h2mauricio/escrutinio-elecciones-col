from pathlib import Path

import easyocr
import numpy as np
from pdf2image import convert_from_path
from PIL import Image

_NULL_CHARS = set("-—–_|xX")


def _is_null(text: str) -> bool:
    return bool(text.strip()) and all(c in _NULL_CHARS or c.isspace() for c in text.strip())


def normalize_vote(text: str) -> int | None:
    """Convert an OCR token to an integer vote count, or None if it represents null."""
    text = text.strip()
    if _is_null(text):
        return None
    digits = "".join(c for c in text if c.isdigit())
    return int(digits) if digits else None


NIVELACION_LABELS = [
    "TOTAL VOTANTES FORMULARIO E-11",
    "TOTAL VOTOS EN LA URNA",
    "TOTAL VOTOS INCINERADOS",
]


def _label_matches(detected: str, target: str, threshold: float = 0.6) -> bool:
    """True if enough words from target appear in detected (tolerates OCR noise)."""
    detected_upper = detected.upper()
    words = target.split()
    matched = sum(1 for w in words if w in detected_upper)
    return matched / len(words) >= threshold


def _read_number_crop(
    reader: easyocr.Reader,
    img: np.ndarray,
    y_top: int,
    y_bottom: int,
    debug_path: Path | None = None,
) -> int | None:
    """
    Crop the right half of the image at the given row and OCR the handwritten number.
    Combines multiple detections left-to-right (hundreds / tens / units may be separate).
    Saves the crop to debug_path if provided.
    """
    img_h, img_w = img.shape[:2]
    x_start = int(img_w * 0.67)
    x_end   = int(img_w * 0.867)
    pad_y    = max(10, (y_bottom - y_top))
    crop_top = max(0, y_top - pad_y)
    crop_bot = min(img_h, y_bottom + pad_y)
    top_trim = int((crop_bot - crop_top) * 0.13)
    crop = img[crop_top + top_trim : crop_bot, x_start:x_end]

    if debug_path is not None:
        Image.fromarray(crop).save(debug_path)
        print(f"  [debug] saved crop → {debug_path}")

    # width_ths: how far apart (in character-height units) two boxes can be and
    # still be merged. Raised from default 0.5 because the digit boxes on the
    # form are separated by an unusually large gap.
    results = reader.readtext(crop, width_ths=2.0, paragraph=False)
    if not results:
        return None

    print(f"  [debug] raw OCR results: {results!r}")
    results.sort(key=lambda r: r[0][0][0])  # left → right
    combined = " ".join(text.strip() for _, text, _ in results if text.strip())
    print(f"  [debug] OCR tokens: {[t for _, t, _ in results]!r} → combined: {combined!r}")
    return normalize_vote(combined)


def read_nivelacion(
    pdf_path: Path,
    debug_dir: Path | None = None,
) -> dict[str, int | None]:
    """
    Extract the three handwritten values from the NIVELACIÓN DE LA MESA table
    using EasyOCR for both label detection and number reading.

    Args:
        pdf_path:  Path to the downloaded acta PDF.
        debug_dir: If given, saves the full page image and each label crop there.

    Returns:
        {
            "TOTAL VOTANTES FORMULARIO E-11": int | None,
            "TOTAL VOTOS EN LA URNA":         int | None,
            "TOTAL VOTOS INCINERADOS":        int | None,
        }
    """
    images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
    img = np.array(images[0])

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).save(debug_dir / "page1_full.png")
        print(f"  [debug] saved full page → {debug_dir / 'page1_full.png'}")

    reader = easyocr.Reader(["es", "en"], gpu=False)

    # Pass 1 — full-page scan to find where each label sits vertically
    label_rows: dict[str, tuple[int, int]] = {}
    for bbox, text, _ in reader.readtext(img):
        for label in NIVELACION_LABELS:
            if label not in label_rows and _label_matches(text, label):
                y_top = int(min(p[1] for p in bbox))
                y_bottom = int(max(p[1] for p in bbox))
                label_rows[label] = (y_top, y_bottom)
                print(f"  [debug] matched {label!r} at y={y_top}–{y_bottom}")
                break  # one detection can only claim one label

    # Pass 2 — for each located label, OCR the cropped number region to its right
    values: dict[str, int | None] = {}
    for label in NIVELACION_LABELS:
        if label not in label_rows:
            print(f"  [!] Label not found: {label!r}")
            values[label] = None
            continue
        y_top, y_bottom = label_rows[label]
        slug = label.lower().replace(" ", "_")
        debug_path = (debug_dir / f"crop_{slug}.png") if debug_dir else None
        values[label] = _read_number_crop(reader, img, y_top, y_bottom, debug_path)

    return values


if __name__ == "__main__":
    pdf_path = Path.home() / "Downloads" / "E14_XXX_X_72_006_000_00_000_X_XXX.pdf"
    debug_dir = Path.home() / "Downloads" / "debug_acta"
    for label, value in read_nivelacion(pdf_path, debug_dir=debug_dir).items():
        print(f"  {label}: {value}")
