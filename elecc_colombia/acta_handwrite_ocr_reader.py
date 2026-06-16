from pathlib import Path

import easyocr
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
from elecc_colombia.config import RAW_DATA_DIR, INTERIM_DATA_DIR

_NULL_CHARS = set("-—–_|xX")
# Single-character mode; whitelist keeps only digits and dash (null marker)
_TESS_CFG = "--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789-"


def _is_null(text: str) -> bool:
    return bool(text.strip()) and all(c in _NULL_CHARS or c.isspace() for c in text.strip())


NIVELACION_LABELS = [
    "TOTAL VOTANTES FORMULARIO E-11",
    "TOTAL VOTOS EN LA URNA",
    "TOTAL VOTOS INCINERADOS",
]


def _label_matches(detected: str, target: str, threshold: float = 0.6) -> bool:
    detected_upper = detected.upper()
    words = target.split()
    matched = sum(1 for w in words if w in detected_upper)
    return matched / len(words) >= threshold


def _crop_number_region(img: np.ndarray, y_top: int, y_bottom: int) -> np.ndarray:
    img_h, img_w = img.shape[:2]
    x_start = int(img_w * 0.67)
    x_end = int(img_w * 0.867)
    pad_y = max(10, (y_bottom - y_top))
    crop_top = max(0, y_top - pad_y)
    crop_bot = min(img_h, y_bottom + pad_y)
    top_trim = int((crop_bot - crop_top) * 0.13)
    return img[crop_top + top_trim : crop_bot, x_start:x_end]


def _split_boxes(crop: np.ndarray) -> list[np.ndarray]:
    """
    Split the three-box number region into individual digit cells.
    Uses column-wise dark-pixel density to locate the two internal dividers,
    falling back to equal thirds when the dividers are not clearly detected.
    """
    gray = (np.mean(crop, axis=2) if crop.ndim == 3 else crop).astype(np.uint8)
    w = gray.shape[1]

    # Fraction of dark pixels per column (dark = form ink / border lines)
    dark_col = (gray < 100).mean(axis=0)
    kernel = np.ones(5) / 5
    smoothed = np.convolve(dark_col, kernel, mode="same")

    # Look for vertical dividers only in the interior (ignore outer border)
    margin = max(int(w * 0.1), 5)
    candidates = [c for c in range(margin, w - margin) if smoothed[c] > 0.4]

    # Cluster into left-half and right-half divider
    mid = w // 2
    left_group = [c for c in candidates if c < mid]
    right_group = [c for c in candidates if c >= mid]
    d1 = int(np.mean(left_group)) if left_group else w // 3
    d2 = int(np.mean(right_group)) if right_group else 2 * w // 3

    b = 3  # pixel border to trim from each box edge
    return [
        crop[:, b : d1 - b],
        crop[:, d1 + b : d2 - b],
        crop[:, d2 + b : w - b],
    ]


def read_digit(img: np.ndarray | Image.Image) -> int | None:
    """
    Read a single handwritten digit from an image crop.

    Args:
        img: A numpy array or PIL Image containing exactly one handwritten digit.

    Returns:
        An integer 0–9, or None if no digit could be read.
    """
    if isinstance(img, np.ndarray):
        img = Image.fromarray(img)
    pil = img.convert("L")
    bw, bh = pil.size
    if bh < 64:
        scale = max(2, 64 // max(bh, 1))
        pil = pil.resize((bw * scale, bh * scale), Image.LANCZOS)
    text = pytesseract.image_to_string(pil, config=_TESS_CFG).strip()
    digits = "".join(c for c in text if c.isdigit())
    return int(digits[0]) if digits else None


def _ocr_box(box: np.ndarray, debug_path: Path | None = None) -> str:
    """Run Tesseract single-character OCR on one digit cell."""
    pil = Image.fromarray(box).convert("L")
    # Upscale small cells so Tesseract has enough resolution
    bw, bh = pil.size
    if bh < 64:
        scale = max(2, 64 // max(bh, 1))
        pil = pil.resize((bw * scale, bh * scale), Image.LANCZOS)
    if debug_path is not None:
        pil.save(debug_path)
    return pytesseract.image_to_string(pil, config=_TESS_CFG).strip()


def _read_number_crop(
    img: np.ndarray,
    y_top: int,
    y_bottom: int,
    debug_path: Path | None = None,
) -> int | None:
    """
    Crop the right-side number region, split into three digit boxes,
    and OCR each box individually with Tesseract.
    """
    crop = _crop_number_region(img, y_top, y_bottom)
    if debug_path is not None:
        Image.fromarray(crop).save(debug_path)
        print(f"  [debug] saved crop → {debug_path}")

    boxes = _split_boxes(crop)
    raw: list[str] = []
    for i, box in enumerate(boxes):
        box_debug = (debug_path.parent / f"{debug_path.stem}_box{i}.png") if debug_path else None
        text = _ocr_box(box, debug_path=box_debug)
        print(f"  [debug] box {i} → {text!r}")
        raw.append(text)

    # All boxes are dashes/blank → this row has no value
    if all(_is_null(t) or not t for t in raw):
        return None

    # Leading null/empty boxes = leading zeros (hundreds/tens not needed)
    digits = ""
    for t in raw:
        if _is_null(t) or not t:
            if digits:  # only pad once we've seen the first real digit
                digits += "0"
        else:
            d = "".join(c for c in t if c.isdigit())
            if d:
                digits += d

    return int(digits) if digits else None


def read_nivelacion(
    pdf_path: Path,
    debug_dir: Path | None = None,
) -> dict[str, int | None]:
    """
    Extract the three handwritten values from the NIVELACIÓN DE LA MESA table.

    Pass 1: EasyOCR locates the printed label rows (reliable for printed text).
    Pass 2: Tesseract reads each digit box individually (--psm 10 single-char mode).

    Args:
        pdf_path:  Path to the downloaded acta PDF.
        debug_dir: If given, saves the full page, each crop, and each digit box.

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

    # Pass 1 — EasyOCR to find where each printed label sits vertically
    reader = easyocr.Reader(["es", "en"], gpu=False)
    label_rows: dict[str, tuple[int, int]] = {}
    for bbox, text, _ in reader.readtext(img):
        for label in NIVELACION_LABELS:
            if label not in label_rows and _label_matches(text, label):
                y_top = int(min(p[1] for p in bbox))
                y_bottom = int(max(p[1] for p in bbox))
                label_rows[label] = (y_top, y_bottom)
                print(f"  [debug] matched {label!r} at y={y_top}–{y_bottom}")
                break

    # Pass 2 — Tesseract per-box for each located label
    values: dict[str, int | None] = {}
    for label in NIVELACION_LABELS:
        if label not in label_rows:
            print(f"  [!] Label not found: {label!r}")
            values[label] = None
            continue
        y_top, y_bottom = label_rows[label]
        slug = label.lower().replace(" ", "_")
        debug_path = (debug_dir / f"crop_{slug}.png") if debug_dir else None
        values[label] = _read_number_crop(img, y_top, y_bottom, debug_path)

    return values


if __name__ == "__main__":
    pdf_path = RAW_DATA_DIR / "E14_XXX_X_72_006_000_00_000_X_XXX.pdf"
    debug_dir = INTERIM_DATA_DIR / "debug_acta"
    for label, value in read_nivelacion(pdf_path, debug_dir=debug_dir).items():
        print(f"  {label}: {value}")
