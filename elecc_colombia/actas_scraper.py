import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright
from elecc_colombia.browser_utils import navigate, select_first_option
from elecc_colombia.config import (DEPARTMENT_ID, 
                                   HEADLESS, 
                                   SLOW_MO, 
                                   BASE_URL, 
                                   READY_SELECTOR)
from loguru import logger



async def click_consultar(page: Page) -> None:
    """Click Consultar and wait for the mesa results table to appear."""
    btn = page.locator("app-custom-button.consult-btn button")
    await btn.wait_for(state="visible", timeout=5_000)
    print("\n── Consultar ──────────────────────────────────")
    print("  Clicking Consultar...")
    await btn.click()
    await page.wait_for_selector(".item-table", state="visible", timeout=15_000)
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

    async with page.expect_download(timeout=30_000) as dl:
        await descargar_btn.click()

    download = await dl.value
    download_pathname = download_dir / download.suggested_filename
    await download.save_as(download_pathname)
    logger.info(f"Downloaded acta to: {download_pathname}")
    
    logger.debug("Acta download process completed.")

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
            mesas = await extract_mesas(page)
            await download_first_acta(page)

            print(f"\nDone — {len(mesas)} mesa(s) extracted.")

        finally:
            await page.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
