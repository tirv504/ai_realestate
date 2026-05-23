"""
Harris County Clerk – May 2026 Foreclosure Deep-Dive Scraper

Pipeline:
  1. Collect all FRCL Doc IDs + sale/filing dates across all pages
  2. For each Doc ID: download PDF → OCR → parse Grantor + Property Address
  3. If address not found in OCR text, try RP.aspx search as fallback
  4. Save to foreclosures_may2026.csv

Output columns:
  name, property_address, instrument_number, filing_date,
  sale_date, document_url, ocr_confidence
"""

import asyncio, io, re, csv
import requests, pytesseract, pdfplumber
from playwright.async_api import async_playwright

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\lirving3661\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

FRCL_URL  = "https://www.cclerk.hctx.net/Applications/WebSearch/FRCL_R.aspx"
RP_URL    = "https://www.cclerk.hctx.net/Applications/WebSearch/RP.aspx"
HCAD_URL  = "https://search.hcad.org/"
BASE      = "https://www.cclerk.hctx.net/Applications/WebSearch/"
OUTPUT    = "foreclosures_may2026_v2.csv"
GRID_ID  = "ctl00_ContentPlaceHolder1_GridView1"
HEADERS  = {"User-Agent": "Mozilla/5.0", "Referer": FRCL_URL}

JS_EXTRACT = f"""() => {{
    const g = document.getElementById('{GRID_ID}');
    if (!g) return {{rows:[], currPage:1, hasMore:false}};
    const rows = Array.from(g.querySelectorAll('a.doclinks')).map(l => {{
        const tr  = l.closest('tr');
        const tds = tr ? Array.from(tr.querySelectorAll('td')) : [];
        return {{
            id:    l.textContent.trim(),
            href:  l.getAttribute('href') || '',
            sale:  tds[2] ? tds[2].textContent.trim() : '',
            filed: tds[3] ? tds[3].textContent.trim() : ''
        }};
    }});
    const pager    = g.querySelector('tr.pagination-ys');
    const spanEl   = pager ? pager.querySelector('span') : null;
    const currPage = spanEl ? (parseInt(spanEl.textContent.trim(), 10) || 1) : 1;
    const links    = pager ? Array.from(pager.querySelectorAll('a'))
                                  .map(a => a.textContent.trim())
                                  .filter((v,i,a)=>a.indexOf(v)===i) : [];
    const hasMore  = links.includes('...') || links.includes(String(currPage+1));
    return {{rows, currPage, hasMore}};
}}"""


# ── Phase 1: collect all Doc IDs ──────────────────────────────────────────────

async def collect_doc_ids(page) -> list[dict]:
    await page.goto(FRCL_URL, wait_until="networkidle", timeout=60000)
    # Year change triggers postback — wait before setting month
    await page.select_option("#ctl00_ContentPlaceHolder1_ddlYear",  "2026")
    await page.wait_for_load_state("networkidle", timeout=30000)
    await page.select_option("#ctl00_ContentPlaceHolder1_ddlMonth", "5")
    await page.click("#ctl00_ContentPlaceHolder1_btnSearch")
    await page.wait_for_load_state("networkidle", timeout=60000)

    docs, seen_first_ids = [], set()
    MAX_PAGES = 500

    while len(seen_first_ids) < MAX_PAGES:
        data      = await page.evaluate(JS_EXTRACT)
        rows      = data["rows"]
        curr_page = data["currPage"]
        has_more  = data["hasMore"]

        if not rows:
            break

        first_id = rows[0]["id"]
        if first_id in seen_first_ids:
            print(f"  !! Loop detected ({first_id}) — done.")
            break
        seen_first_ids.add(first_id)
        print(f"  Page {len(seen_first_ids)}: {len(rows)} records  "
              f"(firstId={first_id}  has_more={has_more})")

        for r in rows:
            docs.append({
                "instrument_number": r["id"],
                "sale_date":         r["sale"],
                "filing_date":       r["filed"],
                "document_url":      BASE + r["href"],
                "_href":             r["href"],
            })

        if not has_more:
            break

        # Click next sequential page or "..." for next block
        next_text = str(curr_page + 1)
        nxt = page.locator(
            f"#{GRID_ID} tr.pagination-ys a"
        ).filter(has_text=re.compile(f"^{next_text}$")).first

        if await nxt.count() == 0:
            nxt = page.locator(
                f"#{GRID_ID} tr.pagination-ys a"
            ).filter(has_text="...").first

        if await nxt.count() == 0:
            break

        await nxt.click()

        # Wait for the UpdatePanel async update to change the first doc ID
        try:
            await page.wait_for_function(
                f"""document.querySelector('#{GRID_ID} a.doclinks') &&
                    document.querySelector('#{GRID_ID} a.doclinks').textContent.trim()
                    !== '{first_id}'""",
                timeout=20000,
            )
        except Exception:
            break  # no change = last page

    return docs


# ── OCR helpers ───────────────────────────────────────────────────────────────

def ocr_pdf(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        parts = []
        for pg in pdf.pages:
            img = pg.to_image(resolution=200).original
            parts.append(pytesseract.image_to_string(img))
    return "\n".join(parts)


# The foreclosure sale is always held at the Bayou City Event Center / commissioner's
# office — exclude these from property address matches.
VENUE_PATTERNS = re.compile(
    r"9401\s+KNIGHT|BAYOU CITY EVENT|COMMISSIONER'?S|MAGNOLIA SOUTH",
    re.IGNORECASE,
)


_JUNK_NAME = re.compile(
    r"^(?:and|or|of|the|in|a|an|by|to|for|with|previously|made|payable)\b",
    re.IGNORECASE,
)

_SUFFIXES = {"JR", "SR", "II", "III", "IV", "ESQ", "JR.", "SR."}

def to_last_first(full_name: str) -> str:
    """'PATRICIA ADELE GODWIN' → 'GODWIN PATRICIA' (RP/HCAD expect LAST FIRST)"""
    parts = full_name.strip().split()
    while parts and parts[-1].upper().rstrip(".") in _SUFFIXES:
        parts.pop()
    if len(parts) < 2:
        return full_name
    return f"{parts[-1]} {parts[0]}"


def parse_grantor(text: str) -> str:
    for pat in [
        # "Grantor(s): NAME" — standard notice of trustee sale format
        r"Grantor(?:\(s\))?[:\s]+([A-Z][A-Za-z ,.'&\-]{3,120}?)(?:\n|$|and\s+Original)",
        # "NAME, as Grantor/Borrower" — no commas in name so we get the last segment
        r"([A-Z][A-Za-z .'&\-]{2,60}(?:,\s*(?:Sr|Jr|II|III|IV)\.?)?),\s*as\s+Grantor(?:/Borrower)?",
        # "NAME, a single/married woman/man/person" — common Texas deed format
        r"([A-Z][A-Za-z .'&\-]{2,60}),\s*(?:a|an)\s+(?:single|married)\s+(?:person|man|woman)",
        # "executed by NAME secures" — standard appointment of substitute trustee
        r"executed\s+by\s+([A-Z][A-Za-z ,.'&\-]{3,100}?)\s+secures",
        # "Deed of Trust [OCR junk] ALL-CAPS-NAME secures" — OCR garbles "executed by"
        r"Deed of Trust[^A-Z]{0,60}([A-Z]{3}[A-Za-z ,.'&\-]{5,120}?)\s+secures",
    ]:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")
            if 3 < len(val) < 150 and not VENUE_PATTERNS.search(val) and not _JUNK_NAME.match(val):
                return val
    return ""


def parse_address(text: str) -> str:
    addr_re = re.compile(
        # House number must start with a non-zero digit (avoids OCR-artifact zeros)
        r"[1-9]\d{1,5}\s+[A-Za-z][A-Za-z0-9 .,'#\-]{4,60}"
        r"(?:STREET|AVENUE|BOULEVARD|DRIVE|LANE|ROAD|COURT|PLACE|CIRCLE|TRAIL|HIGHWAY|FREEWAY|PARKWAY"
        r"|ST|AVE|BLVD|DR|LN|RD|CT|WAY|PL|CIR|TRL|HWY|FWY|PKWY|LOOP|BEND|GROVE|TRACE|RIDGE|PARK)"
        r"[,\s]+[A-Za-z ]{3,25},?\s*TX\s+\d{5}",
        re.IGNORECASE,
    )
    candidates = [m.group(0) for m in addr_re.finditer(text)]
    # Filter out the foreclosure sale venue address
    candidates = [c for c in candidates if not VENUE_PATTERNS.search(c)]
    if candidates:
        return re.sub(r"\s+", " ", candidates[0]).strip()

    # Fallback: look for explicit "Property:" or address label
    m2 = re.search(
        r"(?:Property Address|Property):?\s*\n?\s*(\d{3,6}\s+.{10,100}?(?:TX|Texas)\s+\d{5})",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m2:
        val = re.sub(r"\s+", " ", m2.group(1)).strip()[:150]
        if not VENUE_PATTERNS.search(val):
            return val
    return ""


# ── Phase 2: enrich each doc with OCR ────────────────────────────────────────

def enrich_from_pdf(doc: dict, cookies: dict) -> dict:
    try:
        resp = requests.get(doc["document_url"], cookies=cookies,
                            headers=HEADERS, timeout=30)
        if resp.status_code != 200 or b"%PDF" not in resp.content[:10]:
            doc["ocr_confidence"] = "download_failed"
            return doc
        text = ocr_pdf(resp.content)
        doc["name"]             = parse_grantor(text)
        doc["property_address"] = parse_address(text)
        doc["ocr_confidence"]   = "ocr_ok"
    except Exception as e:
        doc["name"]             = ""
        doc["property_address"] = ""
        doc["ocr_confidence"]   = f"error:{e}"
    return doc


# ── Phase 3: RP fallback ──────────────────────────────────────────────────────

_TX_ADDR = re.compile(r"\bTX\s+\d{5}\b", re.IGNORECASE)

async def _rp_search(page, field_selector: str, value: str) -> str:
    """Fill a field, submit, and return the first valid TX property address found."""
    await page.goto(RP_URL, wait_until="networkidle", timeout=30000)
    await page.fill(field_selector, value)
    await page.click("#ctl00_ContentPlaceHolder1_btnSearch")
    try:
        await page.wait_for_function(
            "document.getElementById('ctl00_ContentPlaceHolder1_lblTotalSearchCount')"
            ".innerText.trim().length > 0",
            timeout=15000,
        )
    except Exception:
        return ""

    rows = page.locator("#ctl00_ContentPlaceHolder1_UpdatePanelResult tr")
    count = await rows.count()
    for i in range(1, min(count, 10)):
        tds = rows.nth(i).locator("td")
        for col in range(await tds.count()):
            cell = (await tds.nth(col).inner_text()).strip()
            if _TX_ADDR.search(cell) and not VENUE_PATTERNS.search(cell):
                return re.sub(r"\s+", " ", cell).strip()
    return ""


async def _hcad_search(page, last_first_name: str) -> str:
    """Search HCAD by owner name (LAST FIRST format) and return first TX address found."""
    await page.goto(HCAD_URL, wait_until="networkidle", timeout=30000)

    # Dump all inputs on first call so we can identify selectors
    inputs = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('input,select,textarea')).map(el => ({
            tag: el.tagName, id: el.id, name: el.name,
            placeholder: el.placeholder, type: el.type
        }))
    """)
    print(f"    [HCAD] Page inputs: {inputs}")

    # Try common HCAD search input selectors
    search_input = None
    for sel in ["input[placeholder*='owner' i]", "input[placeholder*='name' i]",
                "input[placeholder*='search' i]", "input#ownerName",
                "input[name='ownerName']", "input[type='search']", "input[type='text']"]:
        if await page.locator(sel).count() > 0:
            search_input = sel
            break

    if not search_input:
        print("    [HCAD] Could not find search input — page structure unknown")
        return ""

    print(f"    [HCAD] Using input: {search_input!r}")
    await page.fill(search_input, last_first_name)
    await page.keyboard.press("Enter")

    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    # Scan all text on the results page for a TX address
    body_text = await page.inner_text("body")
    for m in re.finditer(
        r"[1-9]\d{1,5}\s+[A-Za-z][A-Za-z0-9 .,'#\-]{4,60}"
        r"(?:STREET|AVENUE|BOULEVARD|DRIVE|LANE|ROAD|COURT|PLACE|CIRCLE|TRAIL|HIGHWAY|FREEWAY|PARKWAY"
        r"|ST|AVE|BLVD|DR|LN|RD|CT|WAY|PL|CIR|TRL|HWY|FWY|PKWY|LOOP|BEND|GROVE|TRACE|RIDGE|PARK)"
        r"[,\s]+[A-Za-z ]{3,25},?\s*TX\s+\d{5}",
        body_text, re.IGNORECASE,
    ):
        addr = re.sub(r"\s+", " ", m.group(0)).strip()
        if not VENUE_PATTERNS.search(addr):
            return addr
    return ""


async def rp_fallback(page, doc: dict) -> dict:
    try:
        name = doc.get("name", "").strip()

        if name and len(name) > 5 and not _JUNK_NAME.match(name):
            last_first = to_last_first(name)

            # Strategy 1: RP search by LAST FIRST name
            print(f"    [RP] Name search: {last_first!r}")
            addr = await _rp_search(page, "#ctl00_ContentPlaceHolder1_txtGrantor", last_first)
            if addr:
                doc["property_address"] = addr
                doc["ocr_confidence"]   = "rp_name"
                print(f"    [RP] Found: {addr[:60]!r}")
                return doc

            # Strategy 2: HCAD search by LAST FIRST name
            print(f"    [HCAD] Name search: {last_first!r}")
            addr = await _hcad_search(page, last_first)
            if addr:
                doc["property_address"] = addr
                doc["ocr_confidence"]   = "hcad_name"
                print(f"    [HCAD] Found: {addr[:60]!r}")
                return doc

        # Strategy 3: RP search by bare numeric instrument ID
        numeric_id = re.sub(r"\D", "", doc["instrument_number"])
        if numeric_id:
            print(f"    [RP] Numeric ID search: {numeric_id}")
            addr = await _rp_search(page, "#ctl00_ContentPlaceHolder1_txtFileNo", numeric_id)
            if addr:
                doc["property_address"] = addr
                doc["ocr_confidence"]   = "rp_id"
                print(f"    [RP] Found: {addr[:60]!r}")

    except Exception as e:
        print(f"    [RP] Error: {e}")

    return doc


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()

        print("=== Phase 1: Collecting all Doc IDs ===")
        docs = await collect_doc_ids(page)
        print(f"Total docs collected: {len(docs)}")

        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}

        print("\n=== Phase 2: OCR deep-dive ===")
        # Tesseract is NOT thread-safe — run OCR sequentially
        rp_needed = []
        for i, doc in enumerate(docs):
            doc.setdefault("name", "")
            doc.setdefault("property_address", "")
            doc.setdefault("ocr_confidence", "")
            print(f"  [{i+1}/{len(docs)}] {doc['instrument_number']}...", end=" ", flush=True)
            doc = enrich_from_pdf(doc, cookies)
            docs[i] = doc
            print(f"name={doc['name'][:30]!r}  addr={doc['property_address'][:30]!r}")
            if not doc["property_address"]:
                rp_needed.append(i)

        # ── Checkpoint: save OCR results before Phase 3 ──────────────────────
        fieldnames = ["name", "property_address", "instrument_number",
                      "filing_date", "sale_date", "document_url", "ocr_confidence"]
        with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(docs)
        print(f"  Checkpoint saved: {len(docs)} records -> {OUTPUT}")

        if rp_needed:
            print(f"\n=== Phase 3: RP fallback for {len(rp_needed)} docs ===")
            for i in rp_needed:
                doc = docs[i]
                print(f"  RP: {doc['instrument_number']}...", end=" ", flush=True)
                docs[i] = await rp_fallback(page, doc)
                print(f"name={docs[i]['name'][:30]!r}")

        await ctx.close()
        await browser.close()

    # Final save with Phase 3 enrichment
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(docs)

    print(f"\nDone. {len(docs)} records -> {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
