"""Test updated parsers on first 5 PDFs."""
import asyncio, io
import requests, pytesseract, pdfplumber
from scrape_foreclosures import parse_grantor, parse_address
from playwright.async_api import async_playwright

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\lirving3661\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)
URL  = "https://www.cclerk.hctx.net/Applications/WebSearch/FRCL_R.aspx"
BASE = "https://www.cclerk.hctx.net/Applications/WebSearch/"

async def get_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx  = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.select_option("#ctl00_ContentPlaceHolder1_ddlYear",  "2026")
        await page.wait_for_load_state("networkidle", timeout=30000)
        await page.select_option("#ctl00_ContentPlaceHolder1_ddlMonth", "5")
        await page.click("#ctl00_ContentPlaceHolder1_btnSearch")
        await page.wait_for_load_state("networkidle", timeout=60000)
        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
        links   = page.locator("a.doclinks")
        docs    = [{"id": (await links.nth(i).inner_text()).strip(),
                    "href": await links.nth(i).get_attribute("href")}
                   for i in range(min(6, await links.count()))]
        await ctx.close(); await browser.close()
    return cookies, docs

def ocr(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(
            pytesseract.image_to_string(pg.to_image(resolution=200).original)
            for pg in pdf.pages
        )

async def main():
    cookies, docs = await get_data()
    headers = {"User-Agent": "Mozilla/5.0", "Referer": URL}
    for d in docs:
        pdf = requests.get(BASE + d["href"], cookies=cookies, headers=headers, timeout=30).content
        text = ocr(pdf)
        name = parse_grantor(text)
        addr = parse_address(text)
        print(f"\n{d['id']}")
        print(f"  Grantor : {name!r}")
        print(f"  Address : {addr!r}")

asyncio.run(main())
