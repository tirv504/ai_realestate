# Houston Pre-Foreclosure AI Pipeline

> An end-to-end Python automation stack for identifying, contacting, and scoring pre-foreclosure leads in Harris County, Texas. Built for real estate wholesalers who want to move faster than everyone else at the courthouse steps.

---

## Pipeline Overview

```
Harris County Clerk                  Your Phone / CRM
       │                                    │
       ▼                                    ▼
scrape_foreclosures.py          responder.py (Flask)
  • Playwright browser           • Twilio SMS webhook
  • FRCL filing scrape           • Claude classifies reply
  • PDF download + OCR           • Auto-responds to seller
  • Name + address extract       • Telegram alert if HOT
  • CSV export                         │
       │                               │
       ▼                               │
BatchSkipTracing.com            offer_estimator.py
  (upload CSV, get phones)        • MAO = ARV×70% − repairs
       │                          • AI deal breakdown (Claude)
       ▼                                │
  blast.py                             ▼
  • Twilio SMS blast          deal_intelligence.py  [coming]
  • Personalized per lead      • Lead scoring (hot/warm/cold)
  • TEST_MODE safety flag      • Urgency + equity analysis
  • 2s delay between sends     • Skip trace queue output
```

---

## Modules

### `scrape_foreclosures.py` — Lead Sourcing Engine
Automates the Harris County Clerk foreclosure search (FRCL filings) using Playwright.

**What it does:**
- Navigates `cclerk.hctx.net` and paginate through all FRCL filings for a given month
- Downloads each PDF instrument and runs Tesseract OCR
- Extracts grantor name (seller) and property address using pattern matching
- Falls back to Harris County Real Property records and HCAD owner search when OCR misses
- Exports a clean CSV ready for skip tracing

**Output columns:** `name`, `property_address`, `instrument_number`, `filing_date`, `sale_date`, `document_url`, `ocr_confidence`

**Usage:**
```bash
python scrape_foreclosures.py
# Edit OUTPUT and ddlMonth at top of file before running
```

**Dependencies:** `playwright`, `pdfplumber`, `pytesseract`, `Pillow`, `requests`

---

### `blast.py` — SMS Outreach Engine
Sends personalized SMS messages to skip-traced leads via the Twilio REST API.

**What it does:**
- Reads a CSV with `phone` and `message` columns
- Normalizes phone numbers to E.164 format
- Sends via Twilio Messaging Service (no SDK — direct REST calls)
- `TEST_MODE = True` by default — sends to your number only before going live

**Usage:**
```bash
# Test (sends 1 message to TEST_PHONE)
python blast.py

# Live blast — flip TEST_MODE = False in the file
python blast.py
```

**Environment variables required:**
```bash
set TWILIO_ACCOUNT_SID=ACxxxx
set TWILIO_AUTH_TOKEN=xxxx
set TWILIO_MESSAGING_SID=MGxxxx
```

---

### `responder.py` — AI Auto-Response + Lead Alert
Flask webhook that receives incoming seller SMS replies through Twilio and responds automatically using Claude.

**What it does:**
- Classifies each seller reply as `INTERESTED` / `NOT_INTERESTED` / `NEEDS_FOLLOWUP` in a single Claude call
- Generates a context-appropriate SMS reply (under 160 chars)
- On `INTERESTED`: fires a Telegram notification with seller name, phone, property address, and the `offer_estimator.py` command to run next
- Looks up lead details from the outreach CSV by phone number

**Usage:**
```bash
# 1. Set environment variables
set ANTHROPIC_API_KEY=sk-ant-xxxx
set TELEGRAM_TOKEN=xxxx         # from @BotFather
set TELEGRAM_CHAT_ID=xxxx       # from getUpdates API

# 2. Start the server
python responder.py

# 3. Expose publicly
ngrok http 5000

# 4. Set Twilio webhook → https://your-ngrok-url.ngrok.io/sms
```

**Telegram bot setup (one-time):**
1. Message `@BotFather` → `/newbot` → copy token
2. Start a chat with your bot
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id`

---

### `offer_estimator.py` — MAO Calculator + AI Deal Breakdown
CLI tool that calculates Maximum Allowable Offer and generates a plain-English deal analysis using Claude.

**The math:**
```
MAO = ARV × 70% − Estimated Repairs
Offer Range = MAO − $15,000  to  MAO − $10,000
Assignment Fee Room = ~$10,000
```

**Usage:**
```bash
# With known ARV (fastest)
python offer_estimator.py "3927 CYPRESS HILL DR HOUSTON TX 77084" --arv 185000 --repairs 25000

# With optional property details
python offer_estimator.py "ADDRESS" --arv 185000 --repairs 25000 --sqft 1450 --year 1968

# Interactive prompt (looks up HCAD value manually)
python offer_estimator.py "ADDRESS"
```

**Sample output:**
```
Property : 3927 CYPRESS HILL DR HOUSTON TX 77084
------------------------------------------------------------
  HCAD Value    : $185,000
  Est. Repairs  : $25,000
  ARV x 70%     : $129,500
  MAO           : $104,500

  >> Offer Range: $89,500 - $94,500
  Assignment $  : ~$10,000

------------------------------------------------------------
AI BREAKDOWN
------------------------------------------------------------
This 1978 property in SW Houston is appraised at $185k — solid
ARV for the submarket. At $25k in repairs, your MAO of $104,500
leaves $10k assignment room and a 30% spread for your end buyer.
Main risk is deferred maintenance on a pre-1980 structure; budget
a contingency for cast iron pipes and HVAC.
```

**Environment variables required:**
```bash
set ANTHROPIC_API_KEY=sk-ant-xxxx
```

---

## Setup

### 1. Clone & install
```bash
git clone https://github.com/tirv504/ai_realestate.git
cd ai_realestate
pip install playwright pdfplumber pytesseract Pillow requests flask anthropic openpyxl
playwright install chromium
```

### 2. System dependency
- **Tesseract OCR** — required for PDF text extraction
  - Windows: download installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  - Add to PATH: `C:\Program Files\Tesseract-OCR`

### 3. Environment variables
```bash
# Anthropic (Claude AI)
set ANTHROPIC_API_KEY=sk-ant-xxxx

# Twilio (SMS)
set TWILIO_ACCOUNT_SID=ACxxxx
set TWILIO_AUTH_TOKEN=xxxx
set TWILIO_MESSAGING_SID=MGxxxx

# Telegram (lead alerts)
set TELEGRAM_TOKEN=xxxx
set TELEGRAM_CHAT_ID=xxxx
```

### 4. Run order
```
1. scrape_foreclosures.py   → foreclosures_[month][year].csv
2. Upload to BatchSkipTracing.com
3. Download results → outreach_ready.csv  (add 'message' column)
4. blast.py                 → SMS blast to leads
5. responder.py             → auto-handle replies + Telegram alerts
6. offer_estimator.py       → run on hot leads after HCAD lookup
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Browser automation | Playwright (Chromium) |
| PDF processing | pdfplumber + Tesseract OCR |
| AI classification & generation | Anthropic Claude (`claude-sonnet-4-6`) |
| SMS delivery | Twilio REST API (no SDK) |
| Lead alert notifications | Telegram Bot API |
| Web server (webhook) | Flask |
| Data processing | Python csv / openpyxl |

---

## Market Focus

This pipeline targets **Harris County, Texas** pre-foreclosure filings (FRCL instrument type). The scraper is calibrated for the Harris County Clerk's ASP.NET UpdatePanel interface. Foreclosure auctions in Harris County occur on the **first Tuesday of each month** at the courthouse steps.

**Priority zip codes** (inner loop, high appreciation):
- 77003, 77011, 77023 — East End / Third Ward
- Houston MSA foreclosure volume averages ~600–900 FRCL filings per month

---

## Roadmap

- [x] Foreclosure scraper (Harris County Clerk FRCL)
- [x] OCR pipeline with HCAD + RP fallback
- [x] BatchSkipTracing CSV formatter
- [x] Twilio SMS blast engine
- [x] Claude AI auto-responder (Flask webhook)
- [x] MAO calculator with AI deal breakdown
- [ ] `deal_intelligence.py` — rule-based lead scoring (hot/warm/cold/dead)
- [ ] Web dashboard — scored leads ranked by urgency
- [ ] Multi-county support (Fort Bend, Montgomery, Brazoria)
- [ ] Comparable sales integration for ARV automation

---

## Disclaimer

This tool accesses publicly available government records (Harris County Clerk, HCAD). All contacted individuals are sourced from public foreclosure filings. Users are responsible for compliance with TCPA, CAN-SPAM, and applicable state telemarketing laws. This is not legal or financial advice.

---

*Built for the Houston wholesale market. First auction: June 3, 2026.*
