"""
Download actas PDFs from the Registraduría website.

Usage examples:

  # Download vuelta02 for all departamentos (default)
  uv run python scripts/download_actas.py

  # Download vuelta01 for all departamentos
  uv run python scripts/download_actas.py --vuelta vuelta01

  # Download specific departamentos for vuelta01
  uv run python scripts/download_actas.py --vuelta vuelta01 -d ARAUCA -d BOLIVAR

  # Override the URL CSV (e.g. for a subset file)
  uv run python scripts/download_actas.py --csv data/external/my_custom.csv

  # Show browser window with slow interactions
  uv run python scripts/download_actas.py --no-headless --slow-mo 400

  # Start fresh log instead of appending
  uv run python scripts/download_actas.py --overwrite-log

The log CSV is written to data/interim/<vuelta>/actas_<hostname>_log.csv so that
multiple computers can download in parallel without overwriting each other's logs.
PDFs are saved to data/raw/<vuelta>/<DEPARTAMENTO>/.
"""

import asyncio
import socket
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger
from playwright.async_api import async_playwright

from elecc_colombia.actas_log import save_actas_log
from elecc_colombia.actas_scraper import download_all_actas, TooManyDownloadErrors
from elecc_colombia.browser_utils import navigate
from elecc_colombia.config import EXTERNAL_DATA_DIR, RAW_DATA_DIR, INTERIM_DATA_DIR, READY_SELECTOR, MAX_DOWNLOAD_ERRORS

app = typer.Typer(add_completion=False)

VALID_VUELTAS = ["vuelta01", "vuelta02"]


def _get_hostname() -> str:
    return socket.gethostname().split(".")[0]


def _log_path(vuelta: str) -> Path:
    hostname = _get_hostname()
    log_dir = INTERIM_DATA_DIR / vuelta
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"actas_{hostname}_log.csv"


async def _run(
    deptos_df: pd.DataFrame,
    vuelta: str,
    headless: bool,
    slow_mo: int,
    overwrite_log: bool,
    max_errors: int,
) -> None:
    log_path = _log_path(vuelta)

    if overwrite_log and log_path.exists():
        log_path.unlink()
        logger.info(f"Cleared existing log: {log_path}")

    async with async_playwright() as pw:
        # TODO: headless mode still fails with ERR_HTTP2_PROTOCOL_ERROR on the Registraduría site
        # despite --disable-http2, --disable-blink-features=AutomationControlled, a real user-agent,
        # and overriding navigator.webdriver. Only --no-headless --slow-mo works reliably for now.
        browser = await pw.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-http2",                        # avoids ERR_HTTP2_PROTOCOL_ERROR on some servers
                "--disable-blink-features=AutomationControlled",  # removes the HeadlessChrome hint from the browser fingerprint
            ],
        )
        context = await browser.new_context(
            # replaces the default "HeadlessChrome/..." UA string that sites commonly block
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        # hides the JS flag that anti-bot scripts use to detect automated browsers
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        for _, row in deptos_df.iterrows():
            departamento = row["DEPARTAMENTO"]
            url = row["URL_ACTAS"]
            download_dir = RAW_DATA_DIR / vuelta / departamento.replace(" ", "_")

            logger.info(f"Starting: {departamento} — {url}")
            page = await context.new_page()
            try:
                await navigate(page, url, READY_SELECTOR)
                # log_path triggers per-mesa saving inside download_all_actas,
                # so each record is written to disk immediately after download.
                # An error mid-departamento will not lose already-saved records.
                records = await download_all_actas(
                    page, download_dir, departamento=departamento,
                    log_path=log_path,
                    max_errors=max_errors,
                )
                logger.success(f"Finished {departamento} — {len(records)} actas logged")
            except TooManyDownloadErrors:
                logger.critical(
                    f"Script stopped after {max_errors} consecutive errors in {departamento}. "
                    f"Check logs/ for details. Re-run the same command to resume."
                )
                break  # stop processing further departamentos
            except Exception as e:
                logger.error(f"Failed {departamento}: {e}")
            finally:
                await page.close()

        await context.close()
        await browser.close()

    logger.info(f"Log saved to: {log_path}")


@app.command()
def main(
    vuelta: Annotated[
        str,
        typer.Option(
            "--vuelta", "-v",
            help=f"Which election round to download. One of: {', '.join(VALID_VUELTAS)}.",
        ),
    ] = "vuelta02",
    departamentos: Annotated[
        list[str] | None,
        typer.Option(
            "--departamentos", "-d",
            help="Departamento name(s) to download. Repeat to add more: -d ARAUCA -d BOLIVAR. "
                 "If omitted, all departamentos in the CSV are downloaded.",
        ),
    ] = None,
    csv: Annotated[
        Path | None,
        typer.Option(
            "--csv", "-c",
            help="CSV file with DEPARTAMENTO and URL_ACTAS columns. "
                 "Defaults to data/external/lista_<vuelta>_actas_urls.csv.",
        ),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--no-headless",
            help="Run browser in headless mode (no visible window). Default: headless.",
        ),
    ] = True,
    slow_mo: Annotated[
        int,
        typer.Option(
            "--slow-mo",
            help="Milliseconds to wait between browser actions. Useful for debugging.",
        ),
    ] = 0,
    overwrite_log: Annotated[
        bool,
        typer.Option(
            "--overwrite-log",
            help="Overwrite this computer's log CSV instead of appending to it.",
        ),
    ] = False,
    max_errors: Annotated[
        int,
        typer.Option(
            "--max-errors",
            help=f"Stop the script after this many failed mesa downloads. Default: {MAX_DOWNLOAD_ERRORS} (from config).",
        ),
    ] = MAX_DOWNLOAD_ERRORS,
) -> None:
    """Download actas PDFs from the Registraduría website for one or more departamentos."""

    if vuelta not in VALID_VUELTAS:
        logger.error(f"Invalid --vuelta '{vuelta}'. Must be one of: {', '.join(VALID_VUELTAS)}")
        raise typer.Exit(1)

    resolved_csv = csv if csv is not None else EXTERNAL_DATA_DIR / f"lista_{vuelta}_actas_urls.csv"

    if not resolved_csv.exists():
        logger.error(f"CSV file not found: {resolved_csv}")
        raise typer.Exit(1)

    deptos_df = pd.read_csv(resolved_csv)
    deptos_df["DEPARTAMENTO"] = deptos_df["DEPARTAMENTO"].str.strip()

    if departamentos:
        requested = [d.upper().strip() for d in departamentos]
        mask = deptos_df["DEPARTAMENTO"].str.upper().isin(requested)
        not_found = set(requested) - set(deptos_df["DEPARTAMENTO"].str.upper())
        if not_found:
            logger.warning(f"Departamento(s) not found in CSV: {', '.join(sorted(not_found))}")
        deptos_df = deptos_df[mask]
        if deptos_df.empty:
            logger.error("No matching departamentos found. Exiting.")
            raise typer.Exit(1)

    hostname = _get_hostname()
    log_path = _log_path(vuelta)
    logger.info(f"Vuelta: {vuelta} | Computer: {hostname} | Log: {log_path}")
    logger.info(f"PDFs → data/raw/{vuelta}/<DEPARTAMENTO>/")
    logger.info(f"Departamentos to download ({len(deptos_df)}): {', '.join(deptos_df['DEPARTAMENTO'])}")
    logger.info(f"Headless: {headless} | Slow-mo: {slow_mo}ms")

    asyncio.run(_run(deptos_df, vuelta=vuelta, headless=headless, slow_mo=slow_mo, overwrite_log=overwrite_log, max_errors=max_errors))


if __name__ == "__main__":
    app()
