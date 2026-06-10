from pathlib import Path

from pdf2image import convert_from_path
import pytesseract


def read_lines(pdf_path: Path, n: int = 10, lang: str = "spa") -> list[str]:
    """Return the first n non-empty printed text lines from a scanned PDF (Tesseract)."""
    images = convert_from_path(pdf_path, first_page=1, last_page=1)
    text = pytesseract.image_to_string(images[0], lang=lang)

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
            if len(lines) == n:
                break

    return lines


if __name__ == "__main__":
    default_path = Path.home() / "Downloads" / "E14_XXX_X_72_006_000_00_000_X_XXX.pdf"
    for line in read_lines(default_path, n=20):
        print(line)
