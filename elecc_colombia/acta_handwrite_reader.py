import base64
from io import BytesIO
from pathlib import Path

import anthropic
import easyocr
import numpy as np
from pdf2image import convert_from_path
from PIL import Image

from dotenv import load_dotenv


load_dotenv()

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


def _crop_number_region(img: np.ndarray, y_top: int, y_bottom: int) -> np.ndarray:
    """Extract the handwritten-number region at the given row."""
    img_h, img_w = img.shape[:2]
    x_start = int(img_w * 0.67)
    x_end   = int(img_w * 0.867)
    pad_y    = max(10, (y_bottom - y_top))
    crop_top = max(0, y_top - pad_y)
    crop_bot = min(img_h, y_bottom + pad_y)
    top_trim = int((crop_bot - crop_top) * 0.13)
    return img[crop_top + top_trim : crop_bot, x_start:x_end]


def _read_number_crop_vision(
    client: anthropic.Anthropic,
    img: np.ndarray,
    y_top: int,
    y_bottom: int,
    debug_path: Path | None = None,
) -> int | None:
    """Read a handwritten three-box number via Claude Vision."""
    crop = _crop_number_region(img, y_top, y_bottom)

    if debug_path is not None:
        Image.fromarray(crop).save(debug_path)
        print(f"  [debug] saved crop → {debug_path}")

    buf = BytesIO()
    Image.fromarray(crop).save(buf, format="PNG")
    image_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=64,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "This image shows a handwritten number written in up to three separate boxes "
                        "(hundreds, tens, units position). Dashes, lines, or X marks in a box mean "
                        "that position is null/blank. Read the digits from left to right and reply "
                        "with ONLY the integer (e.g. '247'), or 'null' if all boxes are dashes/lines."
                    ),
                },
            ],
        }],
    )

    raw = response.content[0].text.strip()
    print(f"  [debug] Claude Vision response: {raw!r}")
    return normalize_vote(raw)


def _read_number_crop_easyocr(
    reader: easyocr.Reader,
    img: np.ndarray,
    y_top: int,
    y_bottom: int,
    debug_path: Path | None = None,
) -> int | None:
    """Read a handwritten number via EasyOCR (kept as fallback)."""
    crop = _crop_number_region(img, y_top, y_bottom)

    if debug_path is not None:
        Image.fromarray(crop).save(debug_path)
        print(f"  [debug] saved crop → {debug_path}")

    results = reader.readtext(crop, width_ths=2.0, paragraph=False)
    if not results:
        return None

    print(f"  [debug] raw OCR results: {results!r}")
    results.sort(key=lambda r: r[0][0][0])
    combined = " ".join(text.strip() for _, text, _ in results if text.strip())
    print(f"  [debug] OCR tokens: {[t for _, t, _ in results]!r} → combined: {combined!r}")
    return normalize_vote(combined)


def read_nivelacion(
    pdf_path: Path,
    debug_dir: Path | None = None,
) -> dict[str, int | None]:
    """
    Extract the three handwritten values from the NIVELACIÓN DE LA MESA table.

    Pass 1 uses EasyOCR to locate label rows (reliable for printed text).
    Pass 2 uses Claude Vision to read the handwritten digit boxes (more reliable
    than EasyOCR for widely-spaced isolated digits).

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

    # Pass 1 — EasyOCR to find where each label sits vertically
    easyocr_reader = easyocr.Reader(["es", "en"], gpu=False)
    label_rows: dict[str, tuple[int, int]] = {}
    for bbox, text, _ in easyocr_reader.readtext(img):
        for label in NIVELACION_LABELS:
            if label not in label_rows and _label_matches(text, label):
                y_top = int(min(p[1] for p in bbox))
                y_bottom = int(max(p[1] for p in bbox))
                label_rows[label] = (y_top, y_bottom)
                print(f"  [debug] matched {label!r} at y={y_top}–{y_bottom}")
                break

    # Pass 2 — Claude Vision to read each handwritten number crop
    vision_client = anthropic.Anthropic()
    values: dict[str, int | None] = {}
    for label in NIVELACION_LABELS:
        if label not in label_rows:
            print(f"  [!] Label not found: {label!r}")
            values[label] = None
            continue
        y_top, y_bottom = label_rows[label]
        slug = label.lower().replace(" ", "_")
        debug_path = (debug_dir / f"crop_{slug}.png") if debug_dir else None
        values[label] = _read_number_crop_vision(vision_client, img, y_top, y_bottom, debug_path)

    return values


if __name__ == "__main__":
    pdf_path = Path.home() / "Downloads" / "E14_XXX_X_72_006_000_00_000_X_XXX.pdf"
    debug_dir = Path.home() / "Downloads" / "debug_acta"
    for label, value in read_nivelacion(pdf_path, debug_dir=debug_dir).items():
        print(f"  {label}: {value}")
