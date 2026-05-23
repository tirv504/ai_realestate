"""
Twilio SMS webhook -> Claude AI -> reply to seller.
On INTERESTED replies: fires a Telegram notification with lead info + offer command.

Setup:
  1. Set environment variables:
       ANTHROPIC_API_KEY   -- your Anthropic key
       TELEGRAM_TOKEN      -- bot token from @BotFather on Telegram
       TELEGRAM_CHAT_ID    -- your personal chat ID (instructions below)
  2. Run:  python responder.py
  3. Expose: ngrok http 5000
  4. Twilio console -> your number -> Messaging -> Webhook:
       https://<your-ngrok-url>/sms  (HTTP POST)

Telegram bot setup (one-time, 2 minutes):
  1. Open Telegram, search @BotFather, send /newbot, follow prompts -> copy token
  2. Start a chat with your new bot (search by name, press Start)
  3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates in browser
  4. Find "chat":{"id": XXXXXXX} -- that number is your TELEGRAM_CHAT_ID
  5. Set both as env vars before running this script
"""

import os
import csv
import threading
import requests
from flask import Flask, request
import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")

CSV_FILE        = r"c:\ai_real_estate_tools\outreach_ready_june2026.csv"
DEFAULT_REPAIRS = 25_000
MAO_FACTOR      = 0.70
ASSIGN_FEE      = 10_000

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Lead lookup -- loaded once at startup
# ---------------------------------------------------------------------------

def _normalize(raw: str) -> str:
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return raw if str(raw).startswith("+") else ""


def _load_leads(path: str) -> dict:
    leads = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                phone = _normalize(row.get("phone", ""))
                if phone:
                    leads[phone] = {
                        "first_name": row.get("first_name", "").strip(),
                        "street":     row.get("street", "").strip(),
                    }
    except FileNotFoundError:
        print(f"[WARN] CSV not found: {path}")
    return leads


LEADS = _load_leads(CSV_FILE)
print(f"[INFO] Loaded {len(LEADS)} leads from CSV")


# ---------------------------------------------------------------------------
# Claude -- classify + reply in one call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a real estate acquisition assistant handling seller SMS replies.

First line of your response MUST be exactly one of:
  CLASSIFICATION: INTERESTED
  CLASSIFICATION: NOT_INTERESTED
  CLASSIFICATION: NEEDS_FOLLOWUP

Second line:
  REPLY: <your SMS reply to the seller>

Rules:
- INTERESTED: any openness to selling or discussing. Reply warmly, ask when \
they're free for a quick 5-minute call.
- NOT_INTERESTED: clear decline. Reply politely and wish them well.
- NEEDS_FOLLOWUP: unclear or needs more info. Ask one clarifying question.
Keep replies under 160 characters. Be warm, not pushy."""


def _call_claude(seller_message: str) -> tuple:
    """Returns (classification, reply_text)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp   = client.messages.create(
        model     ="claude-sonnet-4-6",
        max_tokens=300,
        system    =SYSTEM_PROMPT,
        messages  =[{"role": "user", "content": seller_message}],
    )
    raw = resp.content[0].text.strip()

    classification = "NEEDS_FOLLOWUP"
    reply          = "Thanks for getting back to me! I'll follow up with you shortly."

    for line in raw.splitlines():
        if line.startswith("CLASSIFICATION:"):
            val = line.split(":", 1)[1].strip().upper()
            if val in ("INTERESTED", "NOT_INTERESTED", "NEEDS_FOLLOWUP"):
                classification = val
        elif line.startswith("REPLY:"):
            reply = line.split(":", 1)[1].strip()

    return classification, reply


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

def _send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM NOT CONFIGURED]\n{text}")
        return
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, data={
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }, timeout=10)
    if not resp.ok:
        print(f"[TELEGRAM ERR] {resp.status_code} {resp.text}")


def _build_alert(sender: str, message: str) -> str:
    lead   = LEADS.get(sender, {})
    name   = lead.get("first_name") or "Unknown"
    street = lead.get("street")    or "Unknown address"

    lines = [
        "*HOT LEAD - SELLER INTERESTED*",
        "",
        f"*Name:*     {name}",
        f"*Phone:*    {sender}",
        f"*Property:* {street}, HOUSTON TX",
        "",
        f'*Said:* "{message[:200]}"',
        "",
        "---",
        "*Run offer calc after grabbing HCAD value:*",
        f'`python offer_estimator.py "{street}, HOUSTON TX" --arv [VALUE] --repairs 25000`',
        "",
        "Look up at: https://search.hcad.org/",
    ]
    return "\n".join(lines)


def _notify_background(sender: str, message: str) -> None:
    try:
        _send_telegram(_build_alert(sender, message))
        print(f"[TELEGRAM] Alert sent for {sender}")
    except Exception as e:
        print(f"[ERR] Telegram notification failed: {e}")


# ---------------------------------------------------------------------------
# Flask webhook
# ---------------------------------------------------------------------------

@app.route("/sms", methods=["POST"])
def sms_reply():
    sender = request.form.get("From", "unknown")
    body   = request.form.get("Body", "").strip()

    print(f"\n[IN]  {sender}: {body!r}")

    try:
        classification, reply = _call_claude(body)
    except Exception as e:
        classification = "NEEDS_FOLLOWUP"
        reply = "Hey, thanks for getting back to me! I'll follow up with you shortly."
        print(f"[ERR] Claude API error: {e}")

    print(f"[CLS] {classification}")
    print(f"[OUT] {sender}: {reply!r}")

    if classification == "INTERESTED":
        t = threading.Thread(target=_notify_background, args=(sender, body))
        t.daemon = True
        t.start()

    safe  = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    twiml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{safe}</Message></Response>"
    )
    return twiml, 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    app.run(port=5000, debug=True)
