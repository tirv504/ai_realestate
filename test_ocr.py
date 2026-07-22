"""
OCR pipeline test — first 5 FRCL records.

For each doc:
  1. Open the document PDF URL
  2. Run OCR on every page
  3. Print the raw text lines around 'Grantor' so we can see the format
  4. Show what parse_grantor() extracts
  5. Save results to test_ocr_results.csv
"""
import asyncio, csv, re
import requests, pytesseract
from playwright.async_api import async_playwright
from scrape_foreclosures import (
    ocr_pdf, parse_grantor, parse_address, FRCL_URL, BASE, HEADERS
)

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\lirving3661\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

OUTPUT = "test_ocr_results.csv"
N      = 5   # number of records to test


async def collect_first_n(n: int):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()

        await page.goto(FRCL_URL, wait_until="networkidle", timeout=60000)
        await page.select_option("#ctl00_ContentPlaceHolder1_ddlYear", "2026")
        await page.wait_for_load_state("networkidle", timeout=30000)
        await page.select_option("#ctl00_ContentPlaceHolder1_ddlMonth", "5")
        await page.click("#ctl00_ContentPlaceHolder1_btnSearch")
        await page.wait_for_load_state("networkidle", timeout=60000)

        links   = page.locator("a.doclinks")
        total   = await links.count()
        docs    = []
        for i in range(min(n, total)):
            doc_id = (await links.nth(i).inner_text()).strip()
            href   = await links.nth(i).get_attribute("href")
            # get sale/filing dates from the parent row
            tr   = links.nth(i).locator("xpath=ancestor::tr")
            tds  = tr.locator("td")
            sale  = (await tds.nth(2).inner_text()).strip() if await tds.count() > 2 else ""
            filed = (await tds.nth(3).inner_text()).strip() if await tds.count() > 3 else ""
            docs.append({
                "instrument_number": doc_id,
                "sale_date":         sale,
                "filing_date":       filed,
                "document_url":      BASE + href,
                "_href":             href,
            })

        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
        await ctx.close()
        await browser.close()
    return cookies, docs


def extract_grantor_context(text: str, window: int = 3) -> str:
    """Return lines around 'Grantor' hits, or the full OCR text if none found."""
    lines = text.splitlines()
    out   = []
    for i, line in enumerate(lines):
        if re.search(r"grantor", line, re.IGNORECASE):
            start = max(0, i - 1)
            end   = min(len(lines), i + window + 1)
            out.append("  ---")
            out.extend(f"  {l}" for l in lines[start:end])
    if out:
        return "\n".join(out)
    # No Grantor found — dump full text so we can see what label the doc uses
    return "  (no 'Grantor' line found — full OCR text below)\n" + \
           "\n".join(f"  {l}" for l in lines if l.strip())


def run_ocr_on_doc(doc: dict, cookies: dict) -> dict:
    print(f"\n{'='*60}")
    print(f"Doc    : {doc['instrument_number']}")
    print(f"URL    : {doc['document_url']}")

    resp = requests.get(doc["document_url"], cookies=cookies,
                        headers=HEADERS, timeout=30)
    if resp.status_code != 200 or b"%PDF" not in resp.content[:10]:
        print(f"  ERROR: download failed (status {resp.status_code})")
        doc.update(name="", property_address="", ocr_confidence="download_failed")
        return doc

    print(f"  PDF size: {len(resp.content):,} bytes")
    text = ocr_pdf(resp.content)
    print(f"  OCR chars: {len(text)}")

    print("\n  -- Grantor context (raw OCR) --")
    print(extract_grantor_context(text))

    name = parse_grantor(text)
    addr = parse_address(text)
    print(f"\n  parse_grantor -> {name!r}")
    print(f"  parse_address -> {addr!r}")

    doc.update(name=name, property_address=addr, ocr_confidence="ocr_ok")
    return doc


async def main():
    print(f"Fetching first {N} records from FRCL May 2026...")
    cookies, docs = await collect_first_n(N)
    print(f"Got {len(docs)} docs. Running OCR...\n")

    for i, doc in enumerate(docs):
        docs[i] = run_ocr_on_doc(doc, cookies)

    fieldnames = ["name", "property_address", "instrument_number",
                  "filing_date", "sale_date", "document_url", "ocr_confidence"]
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(docs)

    print(f"\n{'='*60}")
    print(f"Saved {len(docs)} records to {OUTPUT}")
    for d in docs:
        print(f"  {d['instrument_number']:25s}  name={d['name'][:35]!r:37s}  addr={d['property_address'][:35]!r}")


asyncio.run(main())
