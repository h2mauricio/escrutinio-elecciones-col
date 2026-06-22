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

from elecc_colombia.actas_log import ACTAS_LOG_PATH, save_actas_log
from elecc_colombia.actas_scraper import download_all_actas
from elecc_colombia.browser_utils import navigate
from elecc_colombia.config import EXTERNAL_DATA_DIR, RAW_DATA_DIR, READY_SELECTOR

app = typer.Typer(add_completion=False)

DEFAULT_CSV = EXTERNAL_DATA_DIR / "lista_deptos_2da_vuelta_url.csv"


async def _run(
    deptos_df: pd.DataFrame,
    headless: bool,
    slow_mo: int,
    overwrite_log: bool,
) -> None:
    first_write = overwrite_log

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, slow_mo=slow_mo)

        for _, row in deptos_df.iterrows():
            departamento = row["DEPARTAMENTO"]
            url = row["URL_ACTAS"]
            download_dir = RAW_DATA_DIR / departamento.replace(" ", "_")

            logger.info(f"Starting: {departamento} — {url}")
            page = await browser.new_page()
            try:
                await navigate(page, url, READY_SELECTOR)
                records = await download_all_actas(
                    page, download_dir, departamento=departamento
                )
                save_actas_log(records, overwrite=first_write)
                first_write = False
                logger.success(f"Finished {departamento} — {len(records)} actas logged")
            except Exception as e:
                logger.error(f"Failed {departamento}: {e}")
            finally:
                await page.close()

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

    asyncio.run(_run(deptos_df, headless=headless, slow_mo=slow_mo, overwrite_log=overwrite_log))


if __name__ == "__main__":
    app()
