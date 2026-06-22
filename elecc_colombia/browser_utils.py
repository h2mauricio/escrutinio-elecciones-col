from playwright.async_api import Page


async def navigate(page: Page, url: str, ready_selector: str) -> None:
    """Go to a URL and wait until a selector is visible before returning."""
    print(f"Opening: {url}")
    await page.goto(url)
    await page.wait_for_selector(ready_selector, timeout=15_000)
    print("Page loaded.")


async def open_dropdown(page: Page, placeholder: str) -> None:
    """
    Click a custom Angular dropdown by its input placeholder and wait
    until the list items are visible. Tries progressively harder approaches
    if the initial click does not open the dropdown.
    """
    container = page.locator("app-custom-select").filter(
        has=page.locator(f"input[placeholder='{placeholder}']")
    ).locator("div.input-container")

    print(f"Clicking '{placeholder}' container...")
    await container.click()
    await page.wait_for_timeout(1000)

    if await page.locator(".dropdown-list li").count() == 0:
        print("  Dropdown did not open — trying dispatchEvent...")
        await page.eval_on_selector(
            f"input[placeholder='{placeholder}']",
            "el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))"
        )
        await page.wait_for_timeout(1000)

    if await page.locator(".dropdown-list li").count() == 0:
        print("  Trying full event sequence...")
        await page.eval_on_selector(
            f"input[placeholder='{placeholder}']",
            """el => {
                el.dispatchEvent(new Event('focus', {bubbles: true}));
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                el.dispatchEvent(new MouseEvent('mouseup',  {bubbles: true}));
                el.dispatchEvent(new MouseEvent('click',    {bubbles: true}));
            }"""
        )
        await page.wait_for_timeout(1000)

    try:
        await page.wait_for_selector(".dropdown-list li", state="visible", timeout=8_000)
        print("  Dropdown is open!")
    except Exception:
        print("  Trying icon click as last fallback...")
        icon = page.locator("app-custom-select").filter(
            has=page.locator(f"input[placeholder='{placeholder}']")
        ).locator("span.icon")
        await icon.click()
        await page.wait_for_selector(".dropdown-list li", state="visible", timeout=8_000)
        print("  Dropdown opened via icon click!")


async def select_option(page: Page, placeholder: str, index: int = 0) -> str:
    """
    Open a dropdown by placeholder, print all options, and click the one at `index`.
    Uses zero-based indexing. Raises IndexError if index is out of range.
    Returns the text of the selected option.
    """
    await open_dropdown(page, placeholder)

    dropdown = page.locator("app-custom-select").filter(
        has=page.locator(f"input[placeholder='{placeholder}']")
    ).locator(".dropdown-list li")

    items = await dropdown.all()
    print(f"  Found {len(items)} option(s):")
    for i, item in enumerate(items):
        print(f"    [{i}] {(await item.inner_text()).strip()}")

    if index >= len(items):
        raise IndexError(f"index {index} out of range — dropdown has {len(items)} option(s)")

    target = dropdown.nth(index)
    text = (await target.inner_text()).strip()
    print(f"  Selecting [{index}]: '{text}'")
    await target.click()
    await page.wait_for_timeout(800)

    return text


async def select_first_option(page: Page, placeholder: str) -> str:
    """Convenience wrapper — selects the first option (index 0)."""
    return await select_option(page, placeholder, index=0)


async def _open_dropdown_by_label(page: Page, label: str) -> None:
    """Open a filter dropdown by its card-item h4 label, closing any open dropdown first."""
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    container = page.locator(".card-item").filter(
        has=page.locator("h4", has_text=label)
    ).locator("div.input-container")
    await container.click()
    await page.wait_for_selector(".dropdown-list li", state="visible", timeout=8_000)


async def get_options(page: Page, label: str) -> list[str]:
    """Return all option texts for the dropdown identified by its card-item label, without selecting."""
    await _open_dropdown_by_label(page, label)
    texts = await page.locator(".dropdown-list li p").all_inner_texts()
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    return [t.strip() for t in texts]


async def select_option_by_text(page: Page, label: str, text: str) -> None:
    """Select a specific option by its visible text from the dropdown identified by its label."""
    await _open_dropdown_by_label(page, label)
    await page.locator(".dropdown-list li").filter(has_text=text).first.click()
    await page.wait_for_timeout(800)


async def select_page_size(page: Page, size: int = 96) -> None:
    """Select the number of results per page from the button-based 
    dropdown in the results table header."""
    # This dropdown uses a <button> (not <input>), so the placeholder-based helpers don't apply.
    toggle = page.locator(".header-table app-custom-select").filter(
        has=page.locator("button.custom-button")
    ).filter(has=page.locator("img[src*='arrow-bottom']")).locator("div.input-container")

    await toggle.click()
    await page.wait_for_selector(".dropdown-list li", state="visible", timeout=5_000)

    option = page.locator(".dropdown-list li").filter(has_text=f"{size} mesas por")
    await option.click()
    await page.wait_for_selector(".item-table", state="visible", timeout=15_000)
