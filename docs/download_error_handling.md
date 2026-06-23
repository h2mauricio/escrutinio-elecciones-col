# Download Error Handling and Resume

This document describes how `scripts/download_actas.py` and the underlying
`elecc_colombia/actas_scraper.py` handle failures and allow interrupted
downloads to be safely resumed.

---

## Problem

Downloading thousands of PDF actas is a long-running process. Two failure
modes can cause data loss:

1. **Mesa-level timeout** — a single PDF download times out. Previously this
   aborted the entire departamento, losing all remaining mesas.
2. **Process crash / Ctrl-C** — if the script was killed mid-run, no records
   were written to `actas_log.csv` for the current departamento because the
   log was only written once at the end.

---

## Per-mesa saving

`download_all_actas()` now writes one row to `actas_log.csv` **immediately
after each successful PDF download**, before moving on to the next mesa.

```
Mesa 1 downloaded → row written to CSV
Mesa 2 downloaded → row written to CSV
Mesa 3 times out  → error logged, mesa skipped, CSV unchanged
Mesa 4 downloaded → row written to CSV
...
```

If the process is killed at any point, all previously written rows are safe.

This is controlled by the `log_path` parameter passed from the script:

```python
records = await download_all_actas(
    page, download_dir, departamento=departamento,
    log_path=ACTAS_LOG_PATH,   # enables per-mesa saving
)
```

---

## Mesa-level error handling

If a single mesa download fails (timeout, network error, etc.), the error is
logged and that mesa is skipped. The loop continues with the next mesa:

```
ERROR | Failed to download 001_ARAUCA_..._mesa_008.pdf: Timeout 30000ms exceeded
INFO  | Downloading 001_ARAUCA_..._mesa_009.pdf...
```

The failed mesa is **not** recorded in `actas_log.csv` (the file was not saved
to disk, so there is nothing to record). It will be retried automatically on
the next run (see Resume below).

### Stopping after too many errors

If errors accumulate (network down, site unreachable), continuing is pointless.
The `--max-errors` parameter (default `10`) sets the threshold: once that many
mesa downloads fail in a departamento, a `CRITICAL` message is written to the
log file and the script exits:

```
CRITICAL | Stopping CALDAS: reached 10 download errors.
         | 47 actas were saved before stopping.
         | Re-run the same command to resume.
```

To change the threshold:

```bash
# Stop sooner (5 errors)
uv run python scripts/download_actas.py -d CALDAS --max-errors 5 --no-headless --slow-mo 400

# More tolerant (20 errors before stopping)
uv run python scripts/download_actas.py -d CALDAS --max-errors 20 --no-headless --slow-mo 400
```

After the script stops, re-running the same command resumes automatically —
already-saved mesas are skipped and only the failed ones are retried.

---

## Resuming an interrupted download

When `download_all_actas()` starts for a given departamento, it reads
`actas_log.csv` and builds the set of PDF paths already recorded:

```python
already_logged = load_downloaded_paths(departamento, log_path)
```

For each mesa, the check order is:

| Condition | Action |
|---|---|
| Path already in log | Skip entirely (no download, no duplicate log entry) |
| File exists on disk but not in log | Record in log without re-downloading |
| File not on disk | Download, then record |
| Download fails | Log the error, skip recording |

To resume after an interruption, simply re-run the same command:

```bash
uv run python scripts/download_actas.py -d CALDAS --no-headless --slow-mo 400
```

Already-completed mesas are skipped instantly; only missing ones are
downloaded.

---

## Starting a fresh download

To discard the existing log for a departamento and re-download everything:

```bash
uv run python scripts/download_actas.py -d CALDAS --overwrite-log --no-headless --slow-mo 400
```

`--overwrite-log` deletes `actas_log.csv` before the run starts, so every
mesa is treated as new. The PDF files on disk are also re-downloaded if the
file is absent (existing files are still skipped to avoid redundant work).

---

## Key functions

| Function | Location | Purpose |
|---|---|---|
| `load_downloaded_paths(departamento, path)` | `actas_log.py` | Returns the set of `ACTA_PDF` paths already in the log for a departamento |
| `save_actas_log([record], log_path)` | `actas_log.py` | Appends a single record to the CSV immediately after download |
| `download_all_actas(..., log_path)` | `actas_scraper.py` | Orchestrates the per-mesa download loop with error handling and resume logic |
