"""Render thumbnail HTML to PNG using Playwright headless Chromium."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "thumbnail_selfcontained.html"
OUT_PATH = ROOT / "wrinkly_fingers_サムネイル_v3.png"


async def main():
    print(f"Rendering {HTML_PATH.name} ...")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(f"file://{HTML_PATH}", wait_until="networkidle")
        # Wait for fonts to load
        await page.wait_for_timeout(2000)
        # Screenshot the .thumbnail element
        thumb = page.locator("#thumb")
        await thumb.screenshot(path=str(OUT_PATH))
        await browser.close()
    print(f"Saved: {OUT_PATH}")


asyncio.run(main())
