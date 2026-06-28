# Web Scraping — How Actas Are Downloaded

This document explains how the scraper navigates the Registraduría website and
downloads the E-14 acta PDFs for each voting mesa.

---

## Source websites

The Registraduría Nacional publishes digitised acta images for each voting
round at a different subdomain, but with the same URL structure and page format:

| Round | URL pattern |
|---|---|
| Primera vuelta (`vuelta01`) | `https://divulgacione14presidente.registraduria.gov.co/departamento/<ID>` |
| Segunda vuelta (`vuelta02`) | `https://e14segundavueltapresidente.registraduria.gov.co/departamento/<ID>` |

One URL per departamento for each round is listed in:
- `data/external/lista_vuelta01_actas_urls.csv`
- `data/external/lista_vuelta02_actas_urls.csv`

Each page is a single-page Angular application that renders results through
a chain of dropdown filters. The departamentos, municipios, zonas, and puestos
are the same across both rounds; there may be minor differences in mesa
numbering and labeling.

---

## Navigation structure

The actas are nested four levels deep. To reach a specific mesa the scraper
must select one option at each level in order:

```
Departamento (URL)
  └── Municipio   (dropdown)
        └── Zona   (dropdown)
              └── Puesto  (dropdown)
                    └── Mesa(s)  (card list → download button)
```

Selecting a lower-level dropdown dynamically updates the options in the next
one. The scraper therefore cannot pre-fetch all combinations — it must interact
with the page in sequence for every combination.

---

## Step-by-step scraping flow

### 1. Navigate to the departamento page

```python
await navigate(page, url, READY_SELECTOR)
```

`READY_SELECTOR` is the Municipio dropdown input. The scraper waits up to
`PAGE_LOAD_TIMEOUT_MS` (15 s) for it to appear before proceeding, confirming
the Angular app has fully loaded.

### 2. Iterate Municipio → Zona → Puesto

For each level the scraper:

1. Reads all available options with `get_options(page, label)` (opens the
   dropdown, collects the list, closes it).
2. Selects one option with `select_option_by_text(page, label, text)`.
3. Waits for the next dropdown to refresh.

The Municipio dropdown uses the label `"Municipio"`, Zona uses `"Zona"`,
and Puesto uses `"Puesto"` — these map to `<h4>` headings in the Angular
`.card-item` components.

### 3. Query the mesas (Consultar)

After selecting a Puesto, the scraper clicks **Consultar** to trigger the
server query and waits up to `PAGE_LOAD_TIMEOUT_MS` (15 s) for the result
table (`.item-table`) to appear.

The page size is then set to 96 mesas per page so all mesas fit on one page
without pagination.

### 4. Extract mesa availability

Each mesa card has a CSS class `isAvailable` when its acta PDF is ready.
The scraper reads every `.item-table` element, records its name and
availability status, and skips unavailable mesas.

### 5. Download each available acta

For each available mesa the scraper:

1. Clicks the download icon (`.open-pdf`) directly on the mesa card — this
   skips the intermediate preview modal for speed.
2. Waits up to `NETWORK_TIMEOUT_MS` (30 s) for the browser download event.
3. Saves the file to `data/raw/<vuelta>/<DEPARTAMENTO>/<filename>.pdf` using a
   deterministic filename built from Municipio, Zona, Puesto, and mesa index:

```
<MUNICIPIO>_<ZONA>_<PUESTO>_mesa_<NNN>.pdf
e.g. 001_ARAUCA_ZONA_03_02_CONCESCOLAR_LAS_COROCORAS_mesa_008.pdf
```

4. Dismisses the confirmation popup (Aceptar button).
5. Writes one row to `data/interim/<vuelta>/actas_<hostname>_log.csv` immediately.

### 6. Skip already-downloaded mesas

Before starting, the scraper reads this computer's log CSV for the current
departamento and builds a set of already-logged PDF paths. Any mesa whose
path is already in the set is skipped entirely — no download, no duplicate
log entry. This makes every run safely resumable.

---

## Anti-bot measures

The Registraduría site rejects headless Chromium. The browser is launched with
three workarounds:

| Measure | Why |
|---|---|
| `--disable-blink-features=AutomationControlled` | Removes the `HeadlessChrome` hint from the browser fingerprint |
| Custom `user_agent` (Windows Chrome 125) | Replaces the default `HeadlessChrome/...` UA string that sites commonly block |
| `navigator.webdriver = undefined` (init script) | Hides the JS flag that anti-bot scripts detect |

> **Known limitation:** headless mode still fails with `ERR_HTTP2_PROTOCOL_ERROR`
> on this site despite all three mitigations. Use `--no-headless --slow-mo 400`
> until resolved.

---

## Timeouts and retries

All timeout values are defined in `elecc_colombia/config.py`:

| Constant | Value | Used for |
|---|---|---|
| `NETWORK_TIMEOUT_MS` | 30 000 ms | Page navigation, PDF download |
| `PAGE_LOAD_TIMEOUT_MS` | 15 000 ms | Waiting for Angular content to render |

Page navigation retries up to 3 times with exponential backoff (2 s, 4 s, 8 s)
before raising an error (see `browser_utils.navigate`).

PDF download failures are caught per-mesa. After `MAX_DOWNLOAD_ERRORS`
(default 10, set in `config.py`) consecutive failures the script stops and
logs a `CRITICAL` message. Re-running the same command resumes automatically.

---

## Key modules

| Module | Role |
|---|---|
| `elecc_colombia/actas_scraper.py` | Top-level orchestration: iterates Municipio → Zona → Puesto → Mesa, downloads PDFs, writes log |
| `elecc_colombia/browser_utils.py` | Low-level Playwright helpers: `navigate`, `open_dropdown`, `select_option_by_text`, `get_options`, `select_page_size` |
| `elecc_colombia/actas_log.py` | Append-safe CSV writer; `load_downloaded_paths` for resume logic |
| `elecc_colombia/config.py` | All tunable constants: timeouts, error thresholds, paths, selectors |
| `scripts/download_actas.py` | CLI entry point: `--vuelta`, departamento filter, `--max-errors`, `--overwrite-log` |
