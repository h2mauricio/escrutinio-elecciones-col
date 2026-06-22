# Project Organization

```
escrutinio-elecciones-col/
│
├── .env                        <- Local environment variables (not committed)
├── .env.example                <- Template for required environment variables
├── pyproject.toml              <- Package metadata and dependencies (managed by uv)
├── uv.lock                     <- Locked dependency versions
├── Makefile                    <- Convenience commands (make data, make train, …)
│
├── data/
│   ├── external/               <- Reference data from third-party sources
│   │   ├── lista_departamentos_url.csv       <- Departamento URLs (primera vuelta)
│   │   └── lista_deptos_2da_vuelta_url.csv   <- Departamento URLs (segunda vuelta)
│   │
│   ├── raw/                    <- Downloaded PDF actas, organized by departamento
│   │   ├── primera_vuelta/
│   │   │   ├── AMAZONAS/
│   │   │   └── ANTIOQUIA/
│   │   └── ARAUCA/             <- Segunda vuelta downloads (flat departamento folders)
│   │
│   ├── interim/                <- Intermediate data
│   │   ├── actas_log.csv       <- Download log (one row per acta)
│   │   └── crops/              <- Handwritten number crops for ML training
│   │       └── <DEPARTAMENTO>/
│   │           └── <pdf_stem>/
│   │               ├── TOTAL_VOTANTES_FORMULARIO_E_11.png
│   │               ├── IVAN_CEPEDA_CASTRO.png
│   │               └── …
│   │
│   └── processed/              <- Final enriched dataset
│       └── actas_processed.csv <- Printed fields + crop paths per acta
│
├── elecc_colombia/             <- Python package
│   ├── config.py               <- Paths, scraper settings, logger setup
│   ├── browser_utils.py        <- Low-level Playwright helpers (dropdowns, navigation)
│   ├── actas_scraper.py        <- Scraper — downloads PDFs, builds per-acta records
│   ├── actas_log.py            <- Append-safe CSV log writer/reader
│   ├── acta_text_reader.py     <- Tesseract OCR — extracts printed fields from header
│   ├── acta_handwrite_reader.py <- EasyOCR — locates labels, saves handwritten crops
│   ├── actas_processor.py      <- Orchestrates extraction and writes processed CSV
│   └── modeling/
│       ├── train.py            <- Model training (future)
│       └── predict.py          <- Model inference (future)
│
├── notebooks/                  <- Jupyter notebooks, numbered by workflow step
│   ├── 0.01_example_playwright.ipynb          <- Playwright smoke test
│   ├── 0.02_selecting_options_website.ipynb   <- Dropdown interaction exploration
│   ├── 0.03_download_actas_example.ipynb      <- Single-acta download example
│   ├── 1.01_download_actas_create_log.ipynb   <- Full download pipeline
│   ├── 1.02_extract_info_acta_pdf.ipynb       <- Printed-text extraction + crop saving
│   └── 1.03_interpret_handwriting_data_acta.ipynb  <- Handwriting ML (in progress)
│
├── logs/                       <- Daily log files: run_YYYY-MM-DD.log (not committed)
├── models/                     <- Trained model files (future)
├── reports/figures/            <- Generated charts and figures
├── references/                 <- Data dictionaries and explanatory materials
├── tests/                      <- Automated tests
└── docs/                       <- Project documentation
    ├── project_organization.md <- This file
    └── colombia_votacion_header.csv  <- Expected CSV column schema
```

## Data flow

```
data/external/lista_departamentos_url.csv
        │
        ▼
[1.01] actas_scraper.py  ──────────────────►  data/raw/<DEPARTAMENTO>/*.pdf
        │                                               │
        ▼                                               │
data/interim/actas_log.csv                             │
                                                        ▼
                              [1.02] acta_text_reader.py   (Tesseract — printed fields)
                              [1.02] acta_handwrite_reader.py (EasyOCR — crop saving)
                                        │
                                        ▼
                        data/interim/crops/<DEPARTAMENTO>/<pdf_stem>/*.png
                        data/processed/actas_processed.csv
```
