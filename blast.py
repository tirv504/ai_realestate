"""
SMS blast via Twilio — reads outreach_ready_june2026.csv and sends the
pre-built message in the 'message' column to the 'phone' column.

Credentials via environment variables (never hardcode):
    set TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    set TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    set TWILIO_MESSAGING_SID=MGxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""

import os
import csv
import time
import requests

ACCOUNT_SID           = os.getenv("TWILIO_ACCOUNT_SID",    "FILL_IN_YOUR_ACCOUNT_SID")
AUTH_TOKEN            = os.getenv("TWILIO_AUTH_TOKEN",      "FILL_IN_YOUR_AUTH_TOKEN")
MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SID",  "FILL_IN_YOUR_MESSAGING_SID")

CSV_FILE   = r"c:\ai_real_estate_tools\outreach_ready_june2026.csv"
DELAY_SECS = 2

TEST_MODE        = True                  # ← flip to False for the real blast
TEST_PHONE       = "+15044391997"


def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return ""


TWILIO_URL = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"


def send_sms(to: str, body: str) -> str:
    resp = requests.post(
        TWILIO_URL,
        auth=(ACCOUNT_SID, AUTH_TOKEN),
        data={"MessagingServiceSid": MESSAGING_SERVICE_SID, "To": to, "Body": body},
    )
    resp.raise_for_status()
    return resp.json()["sid"]


def main():
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if TEST_MODE:
        rows = rows[:1]
        print(f"TEST MODE — sending 1 message to {TEST_PHONE}\n")
    else:
        print(f"Loaded {len(rows)} rows from {CSV_FILE}\n")

    sent = skipped = errors = 0

    for i, row in enumerate(rows, 1):
        phone_raw = row.get("phone", "").strip()
        body      = row.get("message", "").strip()
        name      = row.get("first_name", "").strip() or "unknown"

        if not phone_raw or not body:
            print(f"  [{i}/{len(rows)}] SKIP  — missing phone or message  ({name})")
            skipped += 1
            continue

        phone = normalize_phone(phone_raw)
        if not phone:
            print(f"  [{i}/{len(rows)}] SKIP  — bad phone '{phone_raw}'  ({name})")
            skipped += 1
            continue

        try:
            sid = send_sms(TEST_PHONE if TEST_MODE else phone, body)
            print(f"  [{i}/{len(rows)}] SENT  {phone}  SID={sid}  ({name})")
            sent += 1
        except Exception as e:
            print(f"  [{i}/{len(rows)}] ERROR {phone}  ({name}): {e}")
            errors += 1

        time.sleep(DELAY_SECS)

    print(f"\nDone. sent={sent}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    main()
