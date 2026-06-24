import asyncio
import re
from pathlib import Path

from playwright.async_api import Page, async_playwright
from elecc_colombia.browser_utils import (navigate, select_first_option, select_page_size,
                                          get_options, select_option_by_text)
from elecc_colombia.config import (DEPARTMENT_ID,
                                   HEADLESS,
                                   SLOW_MO,
                                   BASE_URL,
                                   READY_SELECTOR,
                                   PROJ_ROOT,
                                   MAX_DOWNLOAD_ERRORS,
                                   NETWORK_TIMEOUT_MS,
                                   PAGE_LOAD_TIMEOUT_MS)
from elecc_colombia.actas_log import save_actas_log, load_downloaded_paths
from loguru import logger


class TooManyDownloadErrors(Exception):
    """Raised when failed mesa downloads exceed the max_errors threshold."""


def _sanitize(text: str) -> str:
    """Strip parentheticals and special chars from a dropdown label for use in a filename."""
    text = re.sub(r'\(.*?\)', '', text)        # remove (100%) etc.
    text = re.sub(r'[^\w\s]', '', text)        # remove remaining special chars
    text = re.sub(r'\s+', '_', text.strip())   # collapse whitespace to underscores
    return text.strip('_').upper()


def _build_acta_filename(municipio: str, zona: str, puesto: str, mesa_index: int) -> str:
    return f"{_sanitize(municipio)}_{_sanitize(zona)}_{_sanitize(puesto)}_mesa_{mesa_index + 1:03d}.pdf"


async def click_consultar(page: Page) -> None:
    """Click Consultar and wait for the mesa results table to appear."""
    btn = page.locator("app-custom-button.consult-btn button")
    await btn.wait_for(state="visible", timeout=5_000)
    print("\n── Consultar ──────────────────────────────────")
    print("  Clicking Consultar...")
    await btn.click()
    await page.wait_for_selector(".item-table", state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)
    print("  Results loaded.")


async def extract_mesas(page: Page) -> list[dict]:
    """Extract mesa rows from the results table."""
    items = page.locator(".item-table")
    count = await items.count()
    print(f"\n── Mesas ({count} found) ────────────────────────")

    results = []
    for i in range(count):
        item = items.nth(i)
        classes = (await item.get_attribute("class")) or ""
        available = "isAvailable" in classes

        h3 = item.locator("h3")
        name = (await h3.inner_text()).strip() if await h3.count() > 0 else ""

        row = {"mesa": name, "available": available}
        results.append(row)
        status = "✓" if available else "✗"
        print(f"  [{status}] {name}")

    return results


async def download_first_acta(page: Page, download_dir: Path | None = None) -> None:
    """Click Ver on the first mesa, then Descargar in the popup to save the PDF."""
    if download_dir is None:
        download_dir = Path.home() / "Downloads"
        
    # If download_dir doesn't exist, create it
    download_dir.mkdir(parents=True, exist_ok=True)

    first_item = page.locator(".item-table").first
    ver_btn = first_item.locator("button", has_text="Ver")

    #Print only when we are debugging using loguru 
    logger.debug("Starting acta download process...")
    
    logger.debug("  Clicking Ver on Mesa 1...")
    await ver_btn.click()

    await page.wait_for_selector(".pdf-header", state="visible", timeout=10_000)
    logger.debug("  Modal opened.")

    descargar_btn = page.locator(".container-button button", has_text="Descargar")

    async with page.expect_download(timeout=NETWORK_TIMEOUT_MS) as dl:
        await descargar_btn.click()

    download = await dl.value
    download_pathname = download_dir / download.suggested_filename
    await download.save_as(download_pathname)
    logger.info(f"Downloaded acta to: {download_pathname}")
    
    logger.debug("Acta download process completed.")

    
    
async def download_acta_direct(
    page: Page,
    download_dir: Path | None = None,
    mesa_index: int = 0,
    municipio: str = "",
    zona: str = "",
    puesto: str = "",
    filename_index: int | None = None,
) -> Path:
    """Click the Descargar icon directly on the mesa card, skipping the Ver modal.

    mesa_index: 0-based position within the current results page (for element selection).
    filename_index: 0-based global mesa number used for the filename; defaults to mesa_index.
    """
    if download_dir is None:
        download_dir = Path.home() / "Downloads"

    download_dir.mkdir(parents=True, exist_ok=True)

    selected_item = page.locator(".item-table").nth(mesa_index)
    descargar_icon = selected_item.locator(".open-pdf")

    logger.debug(f"  Clicking Descargar icon on Mesa {mesa_index + 1}...")

    async with page.expect_download(timeout=NETWORK_TIMEOUT_MS) as dl:
        await descargar_icon.click()

    download = await dl.value
    idx = filename_index if filename_index is not None else mesa_index
    filename = _build_acta_filename(municipio, zona, puesto, idx)
    download_pathname = download_dir / filename
    await download.save_as(download_pathname)
    logger.info(f"Downloaded acta to: {download_pathname}")

    aceptar_btn = page.get_by_role("button", name="Aceptar")
    await aceptar_btn.wait_for(state="visible", timeout=10_000)
    await aceptar_btn.click()
    logger.debug("  Popup dismissed.")

    return download_pathname


async def download_all_actas(
    page: Page,
    download_dir: Path,
    departamento: str = "",
    log_path: Path | None = None,
    max_errors: int = MAX_DOWNLOAD_ERRORS,
) -> list[dict]:
    """Download all available actas across every Municipio → Zona → Puesto → Mesa.

    Returns a list of records (one per available mesa) with keys:
    DEPARTAMENTO, MUNICIPIO, ZONA, PUESTO, MESA, ACTA_PDF.
    """
    download_dir.mkdir(parents=True, exist_ok=True)
    records = []

    # Load already-logged paths for this departamento so we can skip them.
    already_logged: set[str] = (
        load_downloaded_paths(departamento, log_path) if log_path is not None else set()
    )
    if already_logged:
        logger.info(f"  Resuming {departamento}: {len(already_logged)} actas already logged — skipping.")

    error_count = 0

    municipios = await get_options(page, "Municipio")
    logger.info(f"Found {len(municipios)} municipio(s).")

    for municipio in municipios:
        await select_option_by_text(page, "Municipio", municipio)
        zonas = await get_options(page, "Zona")
        logger.info(f"  [{municipio}] {len(zonas)} zona(s).")

        for zona in zonas:
            await select_option_by_text(page, "Zona", zona)
            puestos = await get_options(page, "Puesto")
            logger.info(f"    [{zona}] {len(puestos)} puesto(s).")

            for puesto in puestos:
                await select_option_by_text(page, "Puesto", puesto)
                await click_consultar(page)
                await select_page_size(page, size=96)

                result_page_num = 1
                mesa_offset = 0

                while True:
                    mesas = await extract_mesas(page)

                    for i, mesa in enumerate(mesas):
                        global_i = mesa_offset + i
                        if not mesa["available"]:
                            logger.debug(f"      Skipping unavailable {mesa['mesa']}.")
                            continue
                        dest = download_dir / _build_acta_filename(municipio, zona, puesto, global_i)
                        dest_rel = str(dest.relative_to(PROJ_ROOT))
                        if dest_rel in already_logged:
                            logger.debug(f"      Skipping {dest.name} — already in log.")
                            continue
                        if dest.exists():
                            logger.info(f"      Skipping {dest.name} — file exists, adding to log.")
                        else:
                            logger.info(f"      Downloading {dest.name}...")
                            try:
                                await download_acta_direct(
                                    page, download_dir, i, municipio, zona, puesto,
                                    filename_index=global_i,
                                )
                            except Exception as e:
                                error_count += 1
                                logger.error(
                                    f"      Failed to download {dest.name}: {e} "
                                    f"[error {error_count}/{max_errors}]"
                                )
                                if error_count >= max_errors:
                                    logger.critical(
                                        f"Stopping {departamento}: reached {max_errors} download errors. "
                                        f"{len(records)} actas were saved before stopping. "
                                        f"Re-run the same command to resume from where this stopped."
                                    )
                                    raise TooManyDownloadErrors(
                                        f"{max_errors} errors in {departamento}"
                                    )
                                continue  # skip recording this mesa — file is not on disk
                        record = {
                            "DEPARTAMENTO": departamento,
                            "MUNICIPIO": municipio,
                            "ZONA": zona,
                            "PUESTO": puesto,
                            "MESA": mesa["mesa"],
                            "ACTA_PDF": str(dest.relative_to(PROJ_ROOT)),
                        }
                        records.append(record)
                        if log_path is not None:
                            save_actas_log([record], log_path)

                    mesa_offset += len(mesas)

                    paginator = page.locator("app-custom-paginator .page")
                    total_pages = await paginator.count()
                    if result_page_num >= total_pages:
                        break

                    logger.info(f"      Navigating to results page {result_page_num + 1} of {total_pages}...")
                    await paginator.nth(result_page_num).click()
                    await page.wait_for_selector(".item-table", state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)
                    result_page_num += 1

    return records


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        page = await browser.new_page()
        url = BASE_URL + str(DEPARTMENT_ID)
        logger.info(f"Navigating to URL: {url}")
        try:
            await navigate(page, url, READY_SELECTOR)

            print("\n── Municipio ──────────────────────────────────")
            municipio = await select_first_option(page, "seleccione el municipio")
            print(f"  ✓ Municipio selected: {municipio}")

            print("\n── Zona ───────────────────────────────────────")
            zona = await select_first_option(page, "seleccione la zona")
            print(f"  ✓ Zona selected: {zona}")

            print("\n── Puesto ─────────────────────────────────────")
            puesto = await select_first_option(page, "seleccione el puesto")
            print(f"  ✓ Puesto selected: {puesto}")

            await click_consultar(page)
            await select_page_size(page, size=96)
            mesas = await extract_mesas(page)
            await download_first_acta(page)

            print(f"\nDone — {len(mesas)} mesa(s) extracted.")

        finally:
            await page.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
