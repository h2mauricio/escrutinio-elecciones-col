# escrutinio-elecciones-col

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

Scraping, digitization, and analysis of Colombian electoral actas (E-14 forms) for the 2026 presidential election. The project downloads PDF actas from the Registraduría website, extracts printed metadata via OCR, and saves handwritten number crops for ML-based vote counting.

---

## Prerequisites

### uv
This project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management. Install it once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

uv will automatically download and pin **Python 3.14** — no separate Python installation needed.

### System dependencies (macOS)

```bash
# OCR engine for printed text
brew install tesseract tesseract-lang

# PDF-to-image conversion backend
brew install poppler
```

On Ubuntu/Debian:
```bash
sudo apt install tesseract-ocr tesseract-ocr-spa poppler-utils
```

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/mmh54/escrutinio-elecciones-col.git
cd escrutinio-elecciones-col

# 2. Create the virtual environment and install all dependencies
uv sync

# 3. Create the data directory structure
make setup

# 4. Install Playwright and the Chromium browser (used for scraping)
uv run playwright install chromium
```

To run any script or notebook within the project environment, prefix with `uv run`:

```bash
uv run jupyter lab
uv run python elecc_colombia/acta_text_reader.py data/raw/ARAUCA/some_acta.pdf
```

EasyOCR model weights (~300 MB) are downloaded automatically on first use.

---

## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

`.env` contents:

```dotenv
# Log level: DEBUG | INFO | WARNING | ERROR  (default: INFO)
LOG_LEVEL=INFO

# Required only if using Claude Vision for handwritten OCR
ANTHROPIC_API_KEY=your_key_here
```

The project reads this file automatically via `python-dotenv` when any module from `elecc_colombia` is imported. Log files are written daily to `logs/run_YYYY-MM-DD.log`.

---

## Workflow

### 1. Download actas

Run notebook [notebooks/1.01_download_actas_create_log.ipynb](notebooks/1.01_download_actas_create_log.ipynb).

- Reads the list of departamentos from `data/external/lista_departamentos_url.csv`
- Scrapes each departamento's page with Playwright
- Downloads PDFs into `data/raw/<DEPARTAMENTO>/`
- Appends one row per acta to `data/interim/actas_log.csv`

### 2. Extract information from PDFs

Run notebook [notebooks/1.02_extract_info_acta_pdf.ipynb](notebooks/1.02_extract_info_acta_pdf.ipynb).

Calls `process_actas_log()` from `elecc_colombia/actas_processor.py`, which for each PDF:

1. **Printed fields** (Tesseract OCR) — reads the administrative header
2. **Handwritten crops** (EasyOCR) — locates every label row and saves the adjacent handwritten number as a PNG to `data/interim/crops/<DEPARTAMENTO>/<pdf_stem>/<LABEL>.png`

Output: `data/processed/actas_processed.csv`

---

## Data structure

### `data/interim/actas_log.csv` — download log

| Column | Example |
|---|---|
| `RETRIEVAL_TIMESTAMP` | `2026-06-22 15:30:00` |
| `DEPARTAMENTO` | `ARAUCA` |
| `MUNICIPIO` | `001 — ARAUCA (100%)` |
| `ZONA` | `ZONA 01` |
| `PUESTO` | `02 - CONCENTRACION CAMILO TORRES` |
| `MESA` | `Mesa 8` |
| `ACTA_PDF` | `data/raw/ARAUCA/001_ARAUCA_ZONA_01_02_..._mesa_008.pdf` |

### `data/processed/actas_processed.csv` — enriched log

Adds the following columns after processing:

| Source | Columns |
|---|---|
| Printed text (Tesseract) | `DEPARTAMENTO_ACTA`, `MUNICIPIO_ACTA`, `ZONA_ACTA`, `PUESTO_ACTA`, `MESA_ACTA`, `LUGAR_ACTA` |
| Election metadata | `FECHA_ACTA`, `TOTAL_PAGINAS` |
| Form tracking | `NM_FORM`, `KIT`, `CIV` |

### `data/interim/crops/` — handwritten number images

```
crops/
└── ARAUCA/
    └── 001_ARAUCA_ZONA_01_02_CONCENTRACION_CAMILO_TORRES_mesa_008/
        ├── TOTAL_VOTANTES_FORMULARIO_E_11.png
        ├── TOTAL_VOTOS_EN_LA_URNA.png
        ├── TOTAL_VOTOS_INCINERADOS.png
        ├── IVAN_CEPEDA_CASTRO.png
        ├── ABELARDO_DE_LA_ESPRIELLA.png
        ├── VOTOS_EN_BLANCO.png
        ├── VOTOS_NULOS.png
        ├── VOTOS_NO_MARCADOS.png
        └── SUMA_TOTAL.png
```

---

## Key modules

| Module | Purpose |
|---|---|
| `elecc_colombia/config.py` | Paths, scraper settings, logger setup |
| `elecc_colombia/actas_scraper.py` | Playwright scraper — downloads PDFs and builds per-acta records |
| `elecc_colombia/actas_log.py` | Append-safe CSV log writer/reader |
| `elecc_colombia/acta_text_reader.py` | Tesseract OCR — extracts printed fields from acta header |
| `elecc_colombia/acta_handwrite_reader.py` | EasyOCR — locates label rows and saves handwritten crops |
| `elecc_colombia/actas_processor.py` | Orchestrates text extraction + crop saving; writes processed CSV |

---

## Project Organization

See [docs/project_organization.md](docs/project_organization.md) for the full directory tree and data flow diagram.

---

## Information source

Electoral results website:
https://wapp.registraduria.gov.co/electoral/2026/presidente-de-la-republica/
