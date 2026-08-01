"""
LTI Acquisitions Backend — Flask + SQLite + Claude AI

Endpoints:
  GET  /                           Serve lti_acquisitions.html
  GET  /api/leads                  List all leads
  POST /api/leads                  Create lead (start_ai=true generates opening text)
  GET  /api/leads/<id>             Get single lead
  PATCH /api/leads/<id>            Update lead fields
  POST /api/leads/<id>/reply       Process seller reply → Claude extract + next question
  GET  /api/queue                  List message queue (?status=pending&lead_id=...)
  PATCH /api/queue/<id>            Mark queued message sent/failed

Message queue: outbound texts are logged here and printed to console.
Connect blast.py / Twilio once approved — swap queue_msg() to call Twilio directly.

Run:
  set ANTHROPIC_API_KEY=sk-ant-...
  python acquisitions_api.py
  open http://127.0.0.1:5001/
"""

import json
import os
import sqlite3
import time
from pathlib import Path

import anthropic
from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR          = Path(__file__).parent
DB_PATH           = BASE_DIR / "acquisitions.db"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL             = "claude-sonnet-4-6"

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA = """\
CREATE TABLE IF NOT EXISTS leads (
    id           TEXT PRIMARY KEY,
    first        TEXT NOT NULL,
    last         TEXT NOT NULL,
    phone        TEXT DEFAULT '',
    street       TEXT NOT NULL,
    city         TEXT DEFAULT 'Houston',
    state        TEXT DEFAULT 'TX',
    zip          TEXT DEFAULT '',
    ptype        TEXT DEFAULT 'Single Family',
    arv          REAL DEFAULT 0,
    repairs      REAL DEFAULT 0,
    asking       REAL DEFAULT 0,
    source       TEXT DEFAULT 'Direct',
    notes        TEXT DEFAULT '',
    status       TEXT DEFAULT 'New',
    score        INTEGER DEFAULT 0,
    score_parts  TEXT DEFAULT '{}',
    qual         TEXT DEFAULT '{}',
    convo        TEXT DEFAULT '[]',
    timeline     TEXT DEFAULT '[]',
    done         INTEGER DEFAULT 0,
    step         INTEGER DEFAULT 0,
    last_contact INTEGER,
    created_at   INTEGER
);

CREATE TABLE IF NOT EXISTS message_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     TEXT NOT NULL,
    phone       TEXT NOT NULL,
    body        TEXT NOT NULL,
    direction   TEXT DEFAULT 'outbound',
    status      TEXT DEFAULT 'pending',
    created_at  INTEGER,
    sent_at     INTEGER,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);
"""

# Frontend camelCase → DB snake_case for PATCH requests
FIELD_TO_DB: dict[str, str] = {
    "lastContact": "last_contact",
    "scoreParts":  "score_parts",
    "createdAt":   "created_at",
    "status":      "status",
    "score":       "score",
    "done":        "done",
    "step":        "step",
    "notes":       "notes",
    "arv":         "arv",
    "repairs":     "repairs",
    "asking":      "asking",
    "phone":       "phone",
    "qual":        "qual",
    "convo":       "convo",
    "timeline":    "timeline",
}

# DB columns whose values are stored as JSON strings
JSON_DB_COLS = {"score_parts", "qual", "convo", "timeline"}

# DB snake_case → frontend camelCase for API responses
DB_TO_FRONT = {"last_contact": "lastContact", "score_parts": "scoreParts", "created_at": "createdAt"}
# Columns parsed from JSON before sending to frontend
JSON_FRONT_COLS = {"scoreParts", "qual", "convo", "timeline"}


def get_db() -> sqlite3.Connection:
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db


@app.teardown_appcontext
def close_db(_):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()


def row_to_dict(row) -> dict:
    d = {}
    for k, v in dict(row).items():
        key = DB_TO_FRONT.get(k, k)
        if key in JSON_FRONT_COLS and isinstance(v, str):
            try:
                v = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                v = {} if key in ("scoreParts", "qual") else []
        d[key] = v
    d["done"] = bool(d.get("done", 0))
    return d


def now_ms() -> int:
    return int(time.time() * 1000)


def queue_msg(db, lead_id: str, phone: str, body: str, direction: str = "outbound"):
    """Log a message to the queue and print to console for manual sending."""
    db.execute(
        "INSERT INTO message_queue (lead_id, phone, body, direction, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (lead_id, phone, body, direction, "pending", now_ms()),
    )
    tag = "OUT →" if direction == "outbound" else " IN ←"
    print(f"[QUEUE {tag}] {phone or 'no-phone'}: {body[:120]}")


# ---------------------------------------------------------------------------
# Claude AI helpers
# ---------------------------------------------------------------------------

QUAL_FIELD_ORDER = ["interest", "motivation", "timeline", "occupancy", "condition", "debt", "price", "callback"]

EXTRACT_SYSTEM = """\
You qualify real estate seller leads via SMS for LTI Property Advisors in Houston.
Given the seller's reply, extract qualification data and determine next steps.

Qualification fields:
  interest   -- "Yes — actively considering" | "Open to the right offer" | "Not interested"
  motivation -- "Inherited — wants out" | "Repairs are overwhelming" | "Casually exploring" | or free text
  timeline   -- "Within 30 days" | "2–3 months" | "Flexible / no rush" | or free text
  occupancy  -- "Vacant" | "Tenant-occupied" | "Owner-occupied"
  condition  -- "Major repairs needed" | "Light / cosmetic" | "Move-in ready" | or free text
  debt       -- "Owned free & clear" | "Mortgage remaining" | "Unsure of balance" | or free text
  price      -- "Flexible / negotiable" | a dollar amount | "Wants top dollar"
  callback   -- when they said they're available, or "Prefers text only"

Score contribution ranges (set to 0 if a field doesn't apply yet):
  interest:   20 (Yes=20, Open=14, No=0)
  motivation: 20 (Inherited/urgent=20, Repairs overwhelming=18, Casual=6)
  timeline:   20 (≤30 days=20, 2–3 months=10, Flexible=3)
  distress:   15 (Vacant=15, Tenant=6, Owner=2)
  price:      15 (Flexible=15, Specific but reasonable=8, Wants top dollar=2)
  appt:       10 (Agreed to call=10, Text only=0)

Return ONLY valid JSON — no markdown, no explanation:
{
  "field_updates": {"<field>": "<value>"},
  "score_updates": {"<key>": <int>},
  "not_interested": <bool>,
  "next_field": "<motivation|timeline|occupancy|condition|debt|price|callback|done>",
  "suggested_replies": ["<seller reply 1>", "<reply 2>", "<reply 3>"]
}

Rules:
- Only include score_updates keys you can confidently score from this reply
- next_field = "done" when all 8 fields are captured OR seller clearly declined
- not_interested = true only on a clear decline ("no thanks", "not selling", "already listed", etc.)
- suggested_replies: 3 realistic short responses the seller might send (for operator quick-select testing)
"""

QUESTION_SYSTEM = """\
You are Tray, AI acquisitions assistant for LTI Property Advisors in Houston.
Generate the next natural SMS message to qualify a property seller.

Keep it under 155 characters. Sound like a real person — warm, direct, conversational.
Don't re-introduce yourself if the conversation has already started.
Return ONLY the message text, nothing else."""

_QUESTION_FALLBACKS = {
    "interest":   "Hi {first}, this is Tray with LTI Property Advisors — came across your property at {street}. Any chance you'd consider selling?",
    "motivation": "What's the main reason you're thinking about selling?",
    "timeline":   "How soon would you want to move on it if the numbers worked out?",
    "occupancy":  "Is anyone living there right now, or is it vacant?",
    "condition":  "Roughly what kind of shape is it in — anything major it needs?",
    "debt":       "Is there still a mortgage on it, or is it free and clear?",
    "price":      "Do you have a number in mind, or are you open to a fair cash offer?",
    "callback":   "Would you be up for a quick call to go over some options? What time works?",
}


def call_claude_extract(seller_reply: str, context: dict) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    payload = json.dumps({
        "seller":           f"{context['first']} {context['last']}",
        "property":         context["street"],
        "question_asked":   context.get("last_ai_message", ""),
        "seller_reply":     seller_reply,
        "qual_so_far":      context.get("qual", {}),
        "fields_remaining": [f for f in QUAL_FIELD_ORDER if not context.get("qual", {}).get(f)],
    })
    resp = client.messages.create(
        model=MODEL, max_tokens=600,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": payload}],
    )
    raw = resp.content[0].text.strip()
    try:
        data = json.loads(raw)
        return {
            "field_updates":     data.get("field_updates", {}),
            "score_updates":     data.get("score_updates", {}),
            "not_interested":    bool(data.get("not_interested", False)),
            "next_field":        str(data.get("next_field", "done")),
            "suggested_replies": list(data.get("suggested_replies", []))[:3],
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"[WARN] Claude extract returned non-JSON: {raw!r}")
        return {
            "field_updates": {}, "score_updates": {},
            "not_interested": False, "next_field": "done",
            "suggested_replies": [],
        }


def call_claude_question(context: dict, field: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    field_goals = {
        "interest":   "Introduce yourself as Tray from LTI Property Advisors and ask if they'd consider selling",
        "motivation": "Find out why they want to sell",
        "timeline":   "Find out how soon they want to sell",
        "occupancy":  "Find out if property is vacant, tenant-occupied, or owner-occupied",
        "condition":  "Find out what repairs the property needs",
        "debt":       "Find out if there is still a mortgage or other liens",
        "price":      "Find out if they have a price in mind",
        "callback":   "Set up a time for a quick phone call",
    }
    payload = json.dumps({
        "seller_first_name":     context["first"],
        "property_address":      context["street"],
        "qual_captured_so_far":  context.get("qual", {}),
        "next_field_to_capture": field,
        "goal":                  field_goals.get(field, "Continue qualifying"),
        "messages_exchanged":    len(context.get("convo", [])),
    })
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=200,
            system=QUESTION_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[ERR] Claude question ({field}): {e}")
        fallback = _QUESTION_FALLBACKS.get(field, "Tell me more about the property.")
        return fallback.format(first=context.get("first", "there"), street=context.get("street", "the property"))


# ---------------------------------------------------------------------------
# Routes — static
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return send_from_directory(str(BASE_DIR), "lti_acquisitions.html")


# ---------------------------------------------------------------------------
# Routes — leads CRUD
# ---------------------------------------------------------------------------

@app.route("/api/leads", methods=["GET"])
def list_leads():
    db   = get_db()
    rows = db.execute("SELECT * FROM leads ORDER BY last_contact DESC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/leads", methods=["POST"])
def create_lead():
    data     = request.json or {}
    db       = get_db()
    lead_id  = f"ld-{now_ms()}"
    ts       = now_ms()
    start_ai = bool(data.get("start_ai", False))

    convo    = []
    timeline = [{"t": "Lead added", "d": f"Entered manually — {data.get('source', 'Direct')}", "at": ts, "clay": False}]
    status   = "New"

    if start_ai:
        stub = {
            "first": data.get("first", ""), "last": data.get("last", ""),
            "street": data.get("street", ""), "qual": {}, "convo": [],
        }
        opening = call_claude_question(stub, "interest")
        convo.append({"who": "ai", "text": opening, "t": ts})
        timeline.append({"t": "Initial AI message sent", "d": "Opening qualification text generated", "at": ts, "clay": False})
        status = "AI Contacting"

    db.execute("""
        INSERT INTO leads (id,first,last,phone,street,city,state,zip,ptype,
                           arv,repairs,asking,source,notes,status,score,
                           score_parts,qual,convo,timeline,done,step,last_contact,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        lead_id,
        data.get("first", ""), data.get("last", ""),
        data.get("phone", ""), data.get("street", ""),
        data.get("city", "Houston"), data.get("state", "TX"), data.get("zip", ""),
        data.get("ptype", "Single Family"),
        float(data.get("arv") or 0), float(data.get("repairs") or 0), float(data.get("asking") or 0),
        data.get("source", "Direct"), data.get("notes", ""),
        status, 0, "{}", "{}",
        json.dumps(convo), json.dumps(timeline),
        0, 0, ts, ts,
    ))

    if start_ai and data.get("phone") and convo:
        queue_msg(db, lead_id, data["phone"], convo[0]["text"])

    db.commit()
    row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/leads/<lead_id>", methods=["GET"])
def get_lead(lead_id):
    db  = get_db()
    row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def patch_lead(lead_id):
    data = request.json or {}
    db   = get_db()
    row  = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    set_parts, vals = [], []
    for front_key, value in data.items():
        db_col = FIELD_TO_DB.get(front_key)
        if db_col is None:
            continue
        set_parts.append(f"{db_col}=?")
        if db_col in JSON_DB_COLS:
            vals.append(json.dumps(value))
        elif isinstance(value, bool):
            vals.append(int(value))
        else:
            vals.append(value)

    if not set_parts:
        return jsonify(row_to_dict(row))

    already_sets_lc = any(p.startswith("last_contact") for p in set_parts)
    if not already_sets_lc:
        set_parts.append("last_contact=?")
        vals.append(now_ms())

    vals.append(lead_id)
    db.execute(f"UPDATE leads SET {', '.join(set_parts)} WHERE id=?", vals)
    db.commit()
    row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    return jsonify(row_to_dict(row))


@app.route("/api/leads/<lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    db = get_db()
    if not db.execute("SELECT id FROM leads WHERE id=?", (lead_id,)).fetchone():
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM message_queue WHERE lead_id=?", (lead_id,))
    db.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    db.commit()
    return jsonify({"deleted": lead_id})


# ---------------------------------------------------------------------------
# Routes — AI conversation
# ---------------------------------------------------------------------------

@app.route("/api/leads/<lead_id>/reply", methods=["POST"])
def process_reply(lead_id):
    """
    Receives seller's reply text.
    1. Logs inbound message to queue
    2. Claude extracts qual data from the reply
    3. Updates lead score / qualification fields
    4. Claude generates next question (or closes conversation)
    5. Logs outbound question to queue
    Returns updated lead + suggested_replies for quick-select in UI.
    """
    data        = request.json or {}
    seller_text = data.get("text", "").strip()
    if not seller_text:
        return jsonify({"error": "Reply text required"}), 400

    db  = get_db()
    row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    lead = row_to_dict(row)
    if lead.get("done"):
        return jsonify({"error": "Conversation already complete", "lead": lead}), 400

    ts          = now_ms()
    convo       = list(lead["convo"])
    timeline    = list(lead["timeline"])
    qual        = dict(lead["qual"])
    score_parts = dict(lead["scoreParts"])

    convo.append({"who": "seller", "text": seller_text, "t": ts})
    timeline.append({"t": "Seller replied", "d": seller_text[:80], "at": ts, "clay": False})
    queue_msg(db, lead_id, lead.get("phone", ""), seller_text, "inbound")

    last_ai = next((m["text"] for m in reversed(convo[:-1]) if m["who"] == "ai"), "")
    ctx = {
        "first": lead["first"], "last": lead["last"],
        "street": lead["street"],
        "last_ai_message": last_ai,
        "qual": qual, "convo": convo,
    }

    try:
        extraction = call_claude_extract(seller_text, ctx)
    except Exception as e:
        print(f"[ERR] Claude extract: {e}")
        extraction = {"field_updates": {}, "score_updates": {}, "not_interested": False,
                      "next_field": "callback", "suggested_replies": []}

    suggested_replies = extraction.get("suggested_replies", [])
    qual.update(extraction.get("field_updates", {}))

    # Scores only move up
    for k, v in extraction.get("score_updates", {}).items():
        if v > score_parts.get(k, 0):
            score_parts[k] = v

    score          = min(100, sum(score_parts.values()))
    next_field     = extraction.get("next_field", "done")
    not_interested = extraction.get("not_interested", False)

    def _save_and_return(extra_sets: dict):
        db.execute("""
            UPDATE leads SET convo=?,timeline=?,qual=?,score_parts=?,score=?,
                             last_contact=?,status=?,done=?,step=?
            WHERE id=?
        """, (
            json.dumps(convo), json.dumps(timeline), json.dumps(qual),
            json.dumps(score_parts), score, ts,
            extra_sets["status"], int(extra_sets["done"]), extra_sets["step"],
            lead_id,
        ))
        db.commit()
        updated = row_to_dict(db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
        return jsonify({"lead": updated, "suggested_replies": extra_sets.get("sugg", [])})

    # --- Not interested ---
    if not_interested:
        goodbye = f"No problem at all — appreciate your time, {lead['first']}. If anything changes, feel free to reach out!"
        convo.append({"who": "ai", "text": goodbye, "t": ts + 100})
        timeline.append({"t": "Marked Not Interested", "d": "Seller declined", "at": ts + 100, "clay": False})
        queue_msg(db, lead_id, lead.get("phone", ""), goodbye)
        return _save_and_return({"status": "Not Interested", "done": True,
                                 "step": len(QUAL_FIELD_ORDER), "sugg": []})

    # --- Qualification done ---
    if next_field == "done":
        temp       = "Hot" if score >= 75 else "Warm" if score >= 50 else "Nurture" if score >= 25 else "Cold"
        new_status = "Qualified" if score >= 50 else "Follow-Up"
        closing    = f"Perfect — thanks {lead['first']}, really appreciate it. I'll put some numbers together and follow up soon!"
        convo.append({"who": "ai", "text": closing, "t": ts + 100})
        timeline += [
            {"t": f"Motivation score: {score} — {temp}", "d": "Qualification complete", "at": ts + 100, "clay": True},
            {"t": "Marked Qualified" if score >= 50 else "Flagged for follow-up",
             "d": "Ready for acquisition call" if score >= 50 else "Needs nurturing",
             "at": ts + 200, "clay": False},
        ]
        queue_msg(db, lead_id, lead.get("phone", ""), closing)
        return _save_and_return({"status": new_status, "done": True,
                                 "step": len(QUAL_FIELD_ORDER), "sugg": []})

    # --- Continue: generate next question ---
    ctx["qual"] = qual
    next_q = call_claude_question(ctx, next_field)
    convo.append({"who": "ai", "text": next_q, "t": ts + 200})
    timeline.append({"t": f"AI asked: {next_field}", "d": "", "at": ts + 200, "clay": False})
    queue_msg(db, lead_id, lead.get("phone", ""), next_q)

    new_status = lead["status"]
    if new_status in ("New", "Responded"):
        new_status = "AI Contacting"

    return _save_and_return({
        "status": new_status,
        "done":   False,
        "step":   lead.get("step", 0) + 1,
        "sugg":   suggested_replies,
    })


# ---------------------------------------------------------------------------
# Routes — message queue
# ---------------------------------------------------------------------------

@app.route("/api/queue", methods=["GET"])
def list_queue():
    db       = get_db()
    status   = request.args.get("status", "pending")
    lead_id  = request.args.get("lead_id")
    if lead_id:
        rows = db.execute(
            "SELECT * FROM message_queue WHERE lead_id=? AND status=? ORDER BY created_at DESC",
            (lead_id, status),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM message_queue WHERE status=? ORDER BY created_at DESC LIMIT 100",
            (status,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/queue/<int:msg_id>", methods=["PATCH"])
def patch_queue(msg_id):
    data   = request.json or {}
    db     = get_db()
    status = data.get("status", "sent")
    db.execute("UPDATE message_queue SET status=?,sent_at=? WHERE id=?", (status, now_ms(), msg_id))
    db.commit()
    row = db.execute("SELECT * FROM message_queue WHERE id=?", (msg_id,)).fetchone()
    return jsonify(dict(row) if row else {})


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"[INFO] Database: {DB_PATH}")
    print(f"[INFO] Claude model: {MODEL}")
    print(f"[INFO] UI → http://127.0.0.1:5001/")
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
