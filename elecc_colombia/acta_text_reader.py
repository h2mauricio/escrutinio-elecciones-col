import re
from pathlib import Path

from pdf2image import convert_from_path
import pytesseract

_MONTHS = r"(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"

# ZONA, PUESTO, MESA share one line with numeric codes → stop at next whitespace.
# DEPARTAMENTO, MUNICIPIO, LUGAR span the rest of their line.
_FIELD_PATTERNS: dict[str, str] = {
    # Administrative location fields
    "DEPARTAMENTO_ACTA": r"DEPARTAMENTO\s*:\s*(.+?)(?:\n|$)",
    "MUNICIPIO_ACTA":    r"MUNICIPIO\s*:\s*(.+?)(?:\n|$)",
    "ZONA_ACTA":         r"ZONA\s*:\s*(\S+)",
    "PUESTO_ACTA":       r"PUESTO\s*:\s*(\S+)",
    "MESA_ACTA":         r"MESA\s*:\s*(\S+)",
    "LUGAR_ACTA":        r"LUGAR\s*:\s*(.+?)(?:\n|$)",
    # Election metadata
    "FECHA_ACTA":        rf"({_MONTHS}\s+\d{{1,2}}\s+DE\s+\d{{4}})",
    "TOTAL_PAGINAS":     r"Pag[:\s]+\d+\s+de\s+(\d+)",
    # Form tracking numbers (bottom of page: NM No. Form: XXXX  KIT X,XXX  Civ XXXX)
    "NM_FORM":           r"(?:NM|MN)\s+(?:No|vo)[.\s]*(?:Form|rom)[:\s]*(\d+)",
    "KIT":               r"KIT\s+([\d,]+)",
    "CIV":               r"[Cc]iv\s+(\d+)",
}


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


def read_printed_info(pdf_path: Path, lang: str = "spa") -> dict[str, str | None]:
    """Extract printed fields from an acta PDF (page 1, Tesseract OCR).

    Returns a dict with keys:
      Location  — DEPARTAMENTO_ACTA, MUNICIPIO_ACTA, ZONA_ACTA, PUESTO_ACTA, MESA_ACTA, LUGAR_ACTA
      Metadata  — FECHA_ACTA, TOTAL_PAGINAS
      Tracking  — NM_FORM, KIT, CIV
    """
    images = convert_from_path(pdf_path, first_page=1, last_page=1)
    text = pytesseract.image_to_string(images[0], lang=lang)

    result: dict[str, str | None] = {}
    for field, pattern in _FIELD_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        result[field] = match.group(1).strip() if match else None

    return result


if __name__ == "__main__":
    import sys
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "E14_XXX_X_72_006_000_00_000_X_XXX.pdf"
    print("=== printed lines ===")
    for line in read_lines(pdf, n=50):
        print(line)
    print("\n=== extracted fields ===")
    for k, v in read_printed_info(pdf).items():
        print(f"  {k}: {v}")
