"""
Visual test for Phase 3 — RP name search (LAST FIRST) + HCAD fallback.
Tests PATRICIA ADELE GODWIN from FRCL-2026-612.
Run with: python test_bridge.py
"""
import asyncio
from playwright.async_api import async_playwright
from scrape_foreclosures import rp_fallback, to_last_first

TEST_DOCS = [
    {"instrument_number": "FRCL-2026-612",  "name": "PATRICIA ADELE GODWIN",   "property_address": "", "ocr_confidence": ""},
    {"instrument_number": "FRCL-2026-1254", "name": "ELENA PATRICIA PUENTE",   "property_address": "", "ocr_confidence": ""},
    {"instrument_number": "FRCL-2026-1355", "name": "CHRISTOPHER SHERMAN",     "property_address": "", "ocr_confidence": ""},
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page    = await browser.new_page()

        for doc in TEST_DOCS:
            print(f"\n{'='*60}")
            print(f"Instrument : {doc['instrument_number']}")
            print(f"Name       : {doc['name']}")
            print(f"Last-First : {to_last_first(doc['name'])}")
            result = await rp_fallback(page, doc)
            print(f"Address    : {result['property_address']!r}")
            print(f"Confidence : {result['ocr_confidence']!r}")

        input("\nAll done — press ENTER to close the browser...")
        await browser.close()

asyncio.run(main())
