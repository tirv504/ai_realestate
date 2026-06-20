"""
Twilio SMS webhook -> Claude AI -> reply to seller.

Labels:
  INTERESTED      -- any openness to selling; alert + auto-reply
  MAYBE           -- soft interest / on the fence; auto-reply only
  NOT_INTERESTED  -- clear decline; polite goodbye reply
  DO_NOT_CONTACT  -- hostile / explicit opt-out; alert only, no reply
  WRONG_NUMBER    -- not the intended recipient; brief apology reply

Setup:
  1. Set environment variables:
       ANTHROPIC_API_KEY   -- your Anthropic key
       TELEGRAM_TOKEN      -- bot token from @BotFather
       TELEGRAM_CHAT_ID    -- your chat ID (see getUpdates)
  2. Run:  python responder.py
  3. Expose: ngrok http 5000
  4. Twilio -> your number -> Messaging -> Webhook: https://<ngrok>/sms
"""

import json
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

CSV_FILE = r"c:\ai_real_estate_tools\outreach_ready_june2026.csv"

VALID_LABELS    = {"INTERESTED", "MAYBE", "NOT_INTERESTED", "DO_NOT_CONTACT", "WRONG_NUMBER"}
SEND_REPLY_FOR  = {"INTERESTED", "MAYBE", "NOT_INTERESTED", "WRONG_NUMBER"}
ALERT_FOR       = {"INTERESTED", "DO_NOT_CONTACT"}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Lead lookup
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
# Claude -- 5-label classifier, JSON output
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You handle incoming SMS replies for a real estate company that sent outreach about cash offers.

Classify the message into exactly one label and suggest a short, natural reply.

LABELS:
  INTERESTED      -- any openness: asks price, wants more info, says yes/maybe, asks to call
  MAYBE           -- soft / on the fence: "depends", "not sure yet", "possibly", "what would you offer"
  NOT_INTERESTED  -- clear decline: "no thanks", "not selling", "not interested", "pass"
  DO_NOT_CONTACT  -- hostile, angry, or explicit opt-out: "stop texting", "remove me now", threats, profanity-laced refusals
  WRONG_NUMBER    -- wrong person: "wrong number", "I don't own property", "not [name]"

Return ONLY valid JSON with exactly these three keys — no markdown, no explanation:
{
  "label": "<one of the five labels above>",
  "confidence": <float 0.0–1.0>,
  "suggested_reply": "<under 160 chars; warm and direct — avoid robotic phrases like 'Certainly!' or 'I understand your concern'. Write like a real person.>"
}

Reply tone guidelines:
  INTERESTED      -- warm, ask when they're free for a quick call this week
  MAYBE           -- light and low-pressure, one short question to keep it moving
  NOT_INTERESTED  -- brief, gracious, no pushback ("Got it, thanks for letting me know. Best of luck!")
  DO_NOT_CONTACT  -- return the string "NONE" as suggested_reply; we will not reply to this contact
  WRONG_NUMBER    -- short apology, confirm they won't hear from us again"""


def _call_claude(seller_message: str) -> dict:
    """Returns dict with keys: label, confidence, suggested_reply."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp   = client.messages.create(
        model     ="claude-sonnet-4-6",
        max_tokens=300,
        system    =SYSTEM_PROMPT,
        messages  =[{"role": "user", "content": seller_message}],
    )
    raw = resp.content[0].text.strip()

    try:
        data = json.loads(raw)
        label      = str(data.get("label", "")).upper()
        confidence = float(data.get("confidence", 0.5))
        reply      = str(data.get("suggested_reply", "")).strip()

        if label not in VALID_LABELS:
            label = "MAYBE"
        confidence = max(0.0, min(1.0, confidence))

        return {"label": label, "confidence": confidence, "suggested_reply": reply}

    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"[WARN] Claude returned non-JSON: {raw!r}")
        return {
            "label":          "MAYBE",
            "confidence":     0.5,
            "suggested_reply": "Hey, thanks for getting back to me — did you want to chat about the property?",
        }


# ---------------------------------------------------------------------------
# Telegram alerts
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


def _build_interested_alert(sender: str, message: str, confidence: float) -> str:
    lead   = LEADS.get(sender, {})
    name   = lead.get("first_name") or "Unknown"
    street = lead.get("street")    or "Unknown address"
    return "\n".join([
        "*HOT LEAD — SELLER INTERESTED*",
        "",
        f"*Name:*       {name}",
        f"*Phone:*      {sender}",
        f"*Property:*   {street}, Houston TX",
        f"*Confidence:* {confidence:.0%}",
        "",
        f'*Said:* "{message[:200]}"',
        "",
        "*Next step — grab HCAD value, then run:*",
        f'`python offer_estimator.py "{street}, HOUSTON TX" --arv [VALUE] --repairs 25000`',
        "https://search.hcad.org/",
    ])


def _build_dnc_alert(sender: str, message: str) -> str:
    lead   = LEADS.get(sender, {})
    name   = lead.get("first_name") or "Unknown"
    street = lead.get("street")    or "Unknown address"
    return "\n".join([
        "*DO NOT CONTACT — Remove from list*",
        "",
        f"*Name:*     {name}",
        f"*Phone:*    {sender}",
        f"*Property:* {street}",
        "",
        f'*Said:* "{message[:200]}"',
        "",
        "Add this number to your opt-out list and do not text again.",
    ])


def _alert_background(label: str, sender: str, message: str, confidence: float) -> None:
    try:
        if label == "INTERESTED":
            _send_telegram(_build_interested_alert(sender, message, confidence))
        elif label == "DO_NOT_CONTACT":
            _send_telegram(_build_dnc_alert(sender, message))
        print(f"[TELEGRAM] Alert sent ({label}) for {sender}")
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
        result = _call_claude(body)
    except Exception as e:
        print(f"[ERR] Claude API error: {e}")
        result = {
            "label":          "MAYBE",
            "confidence":     0.5,
            "suggested_reply": "Hey, thanks for getting back to me — did you want to chat about the property?",
        }

    label      = result["label"]
    confidence = result["confidence"]
    reply      = result["suggested_reply"]

    print(f"[CLS] {label} ({confidence:.0%})")

    # Telegram alert for INTERESTED and DO_NOT_CONTACT
    if label in ALERT_FOR:
        t = threading.Thread(
            target=_alert_background,
            args=(label, sender, body, confidence),
            daemon=True,
        )
        t.start()

    # Only send SMS reply for certain labels, and only if reply isn't "NONE"
    if label in SEND_REPLY_FOR and reply.upper() != "NONE" and reply:
        print(f"[OUT] {sender}: {reply!r}")
        safe  = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        twiml = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            f"<Response><Message>{safe}</Message></Response>"
        )
    else:
        print(f"[OUT] {sender}: <no reply sent — label={label}>")
        twiml = "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"

    return twiml, 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    app.run(port=5000, debug=True)
