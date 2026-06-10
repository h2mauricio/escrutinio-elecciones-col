import asyncio
from pathlib import Path

from playwright.async_api import async_playwright, Page

from elecc_colombia.browser_utils import navigate, select_first_option

# ── Config ─────────────────────────────────────────────────────────────────────
DEPARTMENT_ID = 72
HEADLESS      = False
SLOW_MO       = 400
# ──────────────────────────────────────────────────────────────────────────────

URL = f"https://divulgacione14presidente.registraduria.gov.co/departamento/{DEPARTMENT_ID}"
READY_SELECTOR = "input[placeholder='seleccione el municipio']"


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


async def download_first_acta(page: Page) -> None:
    """Click Ver on the first mesa, then Descargar in the popup to save the PDF."""
    download_dir = Path.home() / "Downloads"

    first_item = page.locator(".item-table").first
    ver_btn = first_item.locator("button", has_text="Ver")

    print("\n── Acta download ──────────────────────────────")
    print("  Clicking Ver on Mesa 1...")
    await ver_btn.click()

    await page.wait_for_selector(".pdf-header", state="visible", timeout=10_000)
    print("  Modal opened.")

    descargar_btn = page.locator(".container-button button", has_text="Descargar")

    async with page.expect_download(timeout=30_000) as dl:
        await descargar_btn.click()

    download = await dl.value
    dest = download_dir / download.suggested_filename
    await download.save_as(dest)
    print(f"  Saved: {dest}")


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        page = await browser.new_page()

        try:
            await navigate(page, URL, READY_SELECTOR)

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
