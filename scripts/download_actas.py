"""
Download actas PDFs from the Registraduría website.

Usage examples:

  # Download all departamentos (headless, default CSV)
  uv run python scripts/download_actas.py

  # Download specific departamentos
  uv run python scripts/download_actas.py --departamentos ARAUCA --departamentos BOLIVAR

  # Use primera vuelta CSV, show browser window
  uv run python scripts/download_actas.py --csv data/external/lista_departamentos_url.csv --no-headless

  # Start fresh log instead of appending
  uv run python scripts/download_actas.py --overwrite-log
"""

import asyncio
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger
from playwright.async_api import async_playwright

from elecc_colombia.actas_log import ACTAS_LOG_PATH
from elecc_colombia.actas_scraper import download_all_actas, TooManyDownloadErrors
from elecc_colombia.browser_utils import navigate
from elecc_colombia.config import EXTERNAL_DATA_DIR, RAW_DATA_DIR, READY_SELECTOR, MAX_DOWNLOAD_ERRORS

app = typer.Typer(add_completion=False)

DEFAULT_CSV = EXTERNAL_DATA_DIR / "lista_deptos_2da_vuelta_url.csv"


async def _run(
    deptos_df: pd.DataFrame,
    headless: bool,
    slow_mo: int,
    overwrite_log: bool,
    max_errors: int,
) -> None:
    # Delete the log file upfront when overwriting so every per-mesa append
    # starts from a clean slate — no need to track first_write per departamento.
    if overwrite_log and ACTAS_LOG_PATH.exists():
        ACTAS_LOG_PATH.unlink()
        logger.info(f"Cleared existing log: {ACTAS_LOG_PATH}")

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
            download_dir = RAW_DATA_DIR / departamento.replace(" ", "_")

            logger.info(f"Starting: {departamento} — {url}")
            page = await context.new_page()
            try:
                await navigate(page, url, READY_SELECTOR)
                # log_path triggers per-mesa saving inside download_all_actas,
                # so each record is written to disk immediately after download.
                # An error mid-departamento will not lose already-saved records.
                records = await download_all_actas(
                    page, download_dir, departamento=departamento,
                    log_path=ACTAS_LOG_PATH,
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

    logger.info(f"Log saved to: {ACTAS_LOG_PATH}")


@app.command()
def main(
    departamentos: Annotated[
        list[str] | None,
        typer.Option(
            "--departamentos", "-d",
            help="Departamento name(s) to download. Repeat to add more: -d ARAUCA -d BOLIVAR. "
                 "If omitted, all departamentos in the CSV are downloaded.",
        ),
    ] = None,
    csv: Annotated[
        Path,
        typer.Option(
            "--csv", "-c",
            help="CSV file with DEPARTAMENTO and URL_ACTAS columns.",
        ),
    ] = DEFAULT_CSV,
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
            help="Overwrite the log CSV instead of appending to it.",
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

    if not csv.exists():
        logger.error(f"CSV file not found: {csv}")
        raise typer.Exit(1)

    deptos_df = pd.read_csv(csv)
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

    logger.info(f"Departamentos to download ({len(deptos_df)}): {', '.join(deptos_df['DEPARTAMENTO'])}")
    logger.info(f"Headless: {headless} | Slow-mo: {slow_mo}ms | Log: {ACTAS_LOG_PATH}")

    asyncio.run(_run(deptos_df, headless=headless, slow_mo=slow_mo, overwrite_log=overwrite_log, max_errors=max_errors))


if __name__ == "__main__":
    app()
