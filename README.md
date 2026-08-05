# LTI Property Advisors — AI Real Estate Tools

> An end-to-end Python + AI stack for sourcing, contacting, and qualifying motivated seller leads in Houston, Texas. Built for real estate wholesalers who want to move faster than everyone else.

---

## System Overview

```
Harris County Clerk                   Seller's Phone
       │                                    │
       ▼                                    ▼
scrape_foreclosures.py          ┌─────────────────────┐
  • Playwright browser           │  AI Acquisitions    │
  • FRCL filing scrape           │  Assistant          │
  • PDF download + OCR           │  lti_acquisitions   │
  • Name + address extract       │  .html (React UI)   │
  • CSV export                   │  acquisitions_api.py│
       │                         │  • SQLite leads DB  │
       ▼                         │  • Claude AI convo  │
BatchSkipTracing.com             │  • Qual scoring     │
  (upload CSV, get phones)       │  • Message queue    │
       │                         └─────────────────────┘
       ▼                                    │
  blast.py                        responder.py (Flask)
  • Twilio SMS blast               • Twilio SMS webhook
  • Personalized per lead          • Claude classifies reply
  • TEST_MODE safety flag          • Auto-responds to seller
       │                           • Telegram alert if HOT
       ▼
deal_intelligence.py
  • Rule-based lead scoring
  • Hot / warm / cold / dead
  • Skip trace queue output
  • Batch CSV or single record
```

---

## Modules

### `lti_acquisitions.html` + `acquisitions_api.py` — AI Acquisitions Assistant

The core operator tool. A local web app where you manage seller leads, run AI-driven SMS qualification conversations, and track motivation scores and property data.

**What it does:**
- Add leads from any source (pre-foreclosure, absentee, inherited, tax-delinquent)
- `start_ai=true` generates a natural opening SMS via Claude
- Each seller reply is processed by Claude to extract qualification fields and update the motivation score
- Generates the next question targeting uncaptured fields
- Logs all outbound/inbound texts to a message queue for manual sending (Twilio integration pending)
- Conversation, qualification fields, scores, and timeline persist in SQLite across restarts
- Calculates MAO (`ARV × mult − repairs − fee`) and shows a property analysis tab

**Qualification fields tracked:** interest, motivation, timeline, occupancy, condition, debt, asking price, callback availability

**Scoring (100 pts max):**
| Field | Max | Signal |
|---|---|---|
| Interest | 20 | Yes=20, Open=14, No=0 |
| Motivation | 20 | Inherited/urgent=20, Repairs overwhelming=18, Casual=6 |
| Timeline | 20 | ≤30 days=20, 2–3 months=10, Flexible=3 |
| Distress | 15 | Vacant=15, Tenant=6, Owner-occ=2 |
| Price | 15 | Flexible=15, Reasonable=8, Top dollar=2 |
| Appointment | 10 | Agreed to call=10 |

**Usage:**
```powershell
set ANTHROPIC_API_KEY=sk-ant-xxxx
python acquisitions_api.py
# Open http://127.0.0.1:5001/
```

---

### `scrape_foreclosures.py` — Lead Sourcing Engine

Automates the Harris County Clerk foreclosure search (FRCL filings) using Playwright.

**What it does:**
- Navigates `cclerk.hctx.net` and paginates through all FRCL filings for a given month
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

---

### `blast.py` — SMS Outreach Engine

Sends personalized SMS messages to skip-traced leads via the Twilio REST API.

**What it does:**
- Reads a CSV with `phone` and `message` columns
- Normalizes phone numbers to E.164 format
- Sends via Twilio Messaging Service (direct REST, no SDK)
- `TEST_MODE = True` by default — sends to your number only before going live

**Usage:**
```bash
# Test mode (1 message to TEST_PHONE)
python blast.py

# Live blast — flip TEST_MODE = False in the file
python blast.py
```

**Required env vars:**
```powershell
set TWILIO_ACCOUNT_SID=ACxxxx
set TWILIO_AUTH_TOKEN=xxxx
set TWILIO_MESSAGING_SID=MGxxxx
```

---

### `responder.py` — AI Auto-Response + Lead Alert

Flask webhook that receives incoming seller SMS replies via Twilio and responds automatically using Claude.

**What it does:**
- Classifies each reply as one of 5 labels: `INTERESTED` / `CALLBACK_REQUESTED` / `NEEDS_FOLLOWUP` / `NOT_INTERESTED` / `OPT_OUT`
- Generates a context-appropriate SMS reply (under 160 chars)
- On `INTERESTED`: fires a Telegram notification with seller name, phone, and property address
- Looks up lead details from the outreach CSV by phone number

**Usage:**
```bash
set ANTHROPIC_API_KEY=sk-ant-xxxx
set TELEGRAM_TOKEN=xxxx
set TELEGRAM_CHAT_ID=xxxx
python responder.py          # runs on port 5000
ngrok http 5000              # expose publicly
# Set Twilio webhook → https://your-ngrok-url/sms
```

**Telegram bot setup (one-time):**
1. Message `@BotFather` → `/newbot` → copy token
2. Start a chat with your bot
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id`

---

### `deal_intelligence.py` — Rule-Based Lead Scorer

Offline batch scoring tool. No API calls. Runs against a CSV and outputs scored leads with recommended actions, MAO estimates, and a skip-trace queue.

**Usage:**
```bash
# Score a full CSV
python deal_intelligence.py --input foreclosures_may2026.csv

# Score a single record
python deal_intelligence.py --single "3927 Cypress Hill Dr" --arv 185000 --repairs 25000
```

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
python offer_estimator.py "3927 CYPRESS HILL DR" --arv 185000 --repairs 25000
```

**Required env vars:**
```powershell
set ANTHROPIC_API_KEY=sk-ant-xxxx
```

---

## Setup

### 1. Clone & install
```bash
git clone https://github.com/tirv504/ai_realestate.git
cd ai_realestate
pip install -r requirements.txt
pip install playwright pdfplumber pytesseract Pillow openpyxl
playwright install chromium
```

### 2. System dependency
- **Tesseract OCR** — required by `scrape_foreclosures.py` only
  - Windows: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)
  - Add to PATH: `C:\Program Files\Tesseract-OCR`

### 3. Environment variables
```powershell
# Required for acquisitions_api.py, responder.py, offer_estimator.py
set ANTHROPIC_API_KEY=sk-ant-xxxx

# Required for blast.py and responder.py
set TWILIO_ACCOUNT_SID=ACxxxx
set TWILIO_AUTH_TOKEN=xxxx
set TWILIO_MESSAGING_SID=MGxxxx

# Required for responder.py Telegram alerts
set TELEGRAM_TOKEN=xxxx
set TELEGRAM_CHAT_ID=xxxx
```

### 4. Typical workflow
```
1. scrape_foreclosures.py   → foreclosures_[month][year].csv
2. Upload to BatchSkipTracing.com → download with phones
3. deal_intelligence.py     → score and rank leads
4. blast.py                 → SMS blast to priority leads
5. responder.py             → auto-handle inbound replies
6. acquisitions_api.py      → manage hot leads through full AI qualification
7. offer_estimator.py       → run MAO on leads ready for an offer
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI qualification & generation | Anthropic Claude (`claude-sonnet-4-6`) |
| Acquisitions UI | React 18 (CDN/Babel, no build step) |
| Acquisitions backend | Flask + SQLite (WAL mode) |
| SMS delivery | Twilio REST API |
| Lead alert notifications | Telegram Bot API |
| Browser automation | Playwright (Chromium) |
| PDF processing | pdfplumber + Tesseract OCR |
| Inbound SMS webhook | Flask (port 5000) |
| Data processing | Python csv / openpyxl |

---

## Roadmap

- [x] Foreclosure scraper (Harris County Clerk FRCL)
- [x] OCR pipeline with HCAD + RP fallback
- [x] BatchSkipTracing CSV formatter
- [x] Twilio SMS blast engine
- [x] Claude AI auto-responder with 5-label classifier (Flask webhook)
- [x] MAO calculator with AI deal breakdown
- [x] Rule-based lead scoring (`deal_intelligence.py`)
- [x] AI Acquisitions Assistant — full qualification conversation loop, scoring, message queue
- [ ] Connect inbound Twilio SMS to acquisitions DB (responder.py → acquisitions_api.py)
- [ ] CSV bulk import into acquisitions leads DB
- [ ] Live Twilio send from message queue (swap `queue_msg()` for Twilio REST call)
- [ ] Multi-county support (Fort Bend, Montgomery, Brazoria)
- [ ] Comparable sales integration for ARV automation

---

## Disclaimer

This tool accesses publicly available government records (Harris County Clerk, HCAD). All contacted individuals are sourced from public foreclosure filings. Users are responsible for compliance with TCPA, CAN-SPAM, and applicable state telemarketing laws. This is not legal or financial advice.

---

*Built for the Houston wholesale market.*
