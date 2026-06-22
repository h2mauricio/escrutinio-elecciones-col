# escrutinio-elecciones-col

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

Scraping, digitization, and analysis of Colombian electoral actas (E-14 forms) for the 2026 presidential election. The project downloads PDF actas from the Registraduría website, extracts printed metadata via OCR, and saves handwritten number crops for ML-based vote counting.

---

## Contents

- [Prerequisites](#prerequisites)
  - [uv](#uv)
  - [make (Windows only)](#make-windows-only)
  - [System dependencies](#system-dependencies)
- [Installation](#installation)
  - [Running notebooks](#running-notebooks)
- [Configuration](#configuration)
- [Workflow](#workflow)
  - [1. Download actas](#1-download-actas)
  - [2. Extract information from PDFs](#2-extract-information-from-pdfs)
- [Data structure](#data-structure)
- [Key modules](#key-modules)
- [Project Organization](#project-organization)

---

## Prerequisites

### uv
This project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

uv will automatically download and pin **Python 3.14** — no separate Python installation needed.

### make (Windows only)

`make` is not included in Windows by default. Install it with one of the following options:

**Option A — winget** (built into Windows 10/11):
```powershell
winget install GnuWin32.Make
```
After installation, add `C:\Program Files (x86)\GnuWin32\bin` to your `PATH` if it was not added automatically.

**Option B — Chocolatey:**
```powershell
choco install make
```

**Option C — Scoop:**
```powershell
scoop install make
```

**Option D — skip make entirely** and run the equivalent PowerShell command directly:
```powershell
mkdir data\raw, data\interim\crops, data\processed, data\external, logs
```

### System dependencies

**macOS:**
```bash
# OCR engine for printed text
brew install tesseract tesseract-lang

# PDF-to-image conversion backend
brew install poppler
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-spa poppler-utils
```

**Windows:**

Download and install the official binaries:
- **Tesseract**: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) — select "Spanish" language during setup
- **Poppler**: [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases) — extract and add the `bin/` folder to your `PATH`

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/mmh54/escrutinio-elecciones-col.git
cd escrutinio-elecciones-col

# 2. Create the virtual environment and install all dependencies
uv sync

# 3. Create data directories and register the Jupyter kernel
make setup
# On Windows without make, run these two commands instead:
# mkdir data\raw, data\interim\crops, data\processed, data\external, logs
# uv run python -m ipykernel install --user --name=escrutinio-elecciones-col --display-name "escrutinio-elecciones-col"

# 4. Install Playwright and the Chromium browser (used for scraping)
uv run playwright install chromium
```

### Running notebooks

**Option A — VS Code:** after `make setup`, open a notebook, click the kernel picker (top right) → **Jupyter Kernel…** → select `escrutinio-elecciones-col`. If VS Code gets stuck detecting kernels, select the interpreter first via `Ctrl+Shift+P` → **Python: Select Interpreter** → choose `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (macOS/Linux).

**Option B — terminal (always works):**
```bash
uv run jupyter lab
```

To run scripts directly:
```bash
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

**Option A — notebook:**
Run [notebooks/1.01_download_actas_create_log.ipynb](notebooks/1.01_download_actas_create_log.ipynb).

**Option B — command line** (recommended for unattended runs or when Jupyter is unavailable):
```bash
# Download all departamentos (segunda vuelta, headless, appends to existing log)
uv run python scripts/download_actas.py

# Download specific departamentos only
uv run python scripts/download_actas.py -d ARAUCA -d BOLIVAR -d ANTIOQUIA

# Resume a previous run — only downloads missing files, appends to log
uv run python scripts/download_actas.py -d SANTANDER

# Use primera vuelta CSV
uv run python scripts/download_actas.py --csv data/external/lista_departamentos_url.csv

# Start a completely fresh log
uv run python scripts/download_actas.py --overwrite-log

# Show the browser window (useful to watch or debug)
uv run python scripts/download_actas.py -d ARAUCA --no-headless --slow-mo 400
```

Both options write PDFs to `data/raw/<DEPARTAMENTO>/` and append one row per acta to `data/interim/actas_log.csv`.

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
