"""
deal_intelligence.py -- Rule-based lead scoring for Houston wholesale deals.

No external API calls. Fully offline and deterministic.

Usage:
    # Batch mode
    python deal_intelligence.py --input leads.csv --output scored.csv --json scored.json

    # Single record (prints JSON to stdout)
    python deal_intelligence.py \\
        --address "3927 CYPRESS HILL DR HOUSTON TX 77084" \\
        --seller "JESSIE LEE" \\
        --sale-date 2026-06-03 \\
        --phone "+12137332966" \\
        --assessed-value 142000 \\
        --year-built 1978 \\
        --sqft 1350 \\
        --reply "how much are you offering"
"""

import re
import csv
import json
import sys
import argparse
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY_ZIPS = {"77003", "77011", "77023"}

DEFAULT_SQFT    = 1_200
REPAIR_RATE_NEW = 15        # $/sqft post-1980
REPAIR_RATE_OLD = 20        # $/sqft pre-1980
MAO_FACTOR      = 0.70
ARV_UPLIFT      = 1.10      # conservative: assessed * 1.10 = estimated ARV
ASSIGN_FEE      = 10_000

# Ranking for priority zip boost (never shown externally)
_SCORE_RANK = {"dead": 0, "cold": 1, "warm": 2, "hot": 3}
_RANK_SCORE = {v: k for k, v in _SCORE_RANK.items()}

# Seller intent keyword lists
_INTERESTED_PHRASES = [
    "how much", "what are you offering", "what's your offer", "whats your offer",
    "call me", "i'd consider", "i would consider", "might consider", "tell me more",
]
_INTERESTED_WORDS = {"yes", "yeah", "yep", "sure", "interested", "maybe", "possibly"}

_HARD_STOP_PHRASES = [
    "stop texting", "stop calling", "don't contact", "do not contact",
    "remove me", "leave me alone",
]

_SOFT_NO_PHRASES = [
    "not interested", "no thanks", "already sold", "already handled",
    "have an agent", "already have an agent", "going through",
]
_SOFT_NO_WORDS = {"listed"}

# Column aliasing — maps spec field names to CSV column name variants
_COLUMN_ALIASES = {
    "property_address": ["property_address", "address", "street"],
    "seller_name":      ["seller_name", "name", "first_name", "owner"],
    "sale_date":        ["sale_date"],
    "phone":            ["phone", "phone_number", "mobile"],
    "assessed_value":   ["assessed_value", "appraised_value", "hcad_value", "market_value"],
    "year_built":       ["year_built", "year", "built"],
    "sqft":             ["sqft", "square_feet", "sq_ft", "living_area"],
    "seller_reply":     ["seller_reply", "reply", "response", "seller_response"],
}


# ---------------------------------------------------------------------------
# Pure scoring functions  (no I/O — all testable in isolation)
# ---------------------------------------------------------------------------

def _extract_zip(address: str) -> str:
    """Return the first 5-digit ZIP code found in address, or ''."""
    m = re.search(r"\b(\d{5})\b", address or "")
    return m.group(1) if m else ""


def _days_until(sale_date_str: str, run_date: date = None) -> Optional[int]:
    """Days from run_date to sale_date. Negative = past. None = unparseable."""
    if not sale_date_str or not str(sale_date_str).strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            sale  = datetime.strptime(str(sale_date_str).strip(), fmt).date()
            today = run_date or date.today()
            return (sale - today).days
        except ValueError:
            continue
    return None


def urgency_score(sale_date_str: str, run_date: date = None) -> int:
    """Return urgency 1-5 based on days until auction date."""
    days = _days_until(sale_date_str, run_date)
    if days is None or days < 0:
        return 1
    if days <= 7:
        return 5
    if days <= 14:
        return 4
    if days <= 30:
        return 3
    if days <= 60:
        return 2
    return 1


def classify_intent(reply: str) -> str:
    """
    Classify seller SMS reply intent.
    Returns one of: INTERESTED | NOT_INTERESTED_HARD | NOT_INTERESTED_SOFT
                    NEEDS_FOLLOWUP | NO_REPLY
    """
    if not reply or not str(reply).strip():
        return "NO_REPLY"

    text  = str(reply).lower().strip()
    words = set(re.findall(r"\b\w+\b", text))

    # Hard stops checked first — no contact again
    if any(p in text for p in _HARD_STOP_PHRASES):
        return "NOT_INTERESTED_HARD"
    # Bare "stop" alone (TCPA opt-out keyword)
    if words == {"stop"}:
        return "NOT_INTERESTED_HARD"

    # Interested phrases checked before word-level (phrases are more specific)
    if any(p in text for p in _INTERESTED_PHRASES):
        return "INTERESTED"

    # Soft no PHRASES before interested WORDS — prevents "not interested"
    # matching the bare word "interested" before the negation is seen
    if any(p in text for p in _SOFT_NO_PHRASES):
        return "NOT_INTERESTED_SOFT"
    if words & _SOFT_NO_WORDS:
        return "NOT_INTERESTED_SOFT"

    # Interested word-level (after negation phrases are ruled out)
    if words & _INTERESTED_WORDS:
        return "INTERESTED"

    return "NEEDS_FOLLOWUP"


def estimate_equity(
    assessed_value: Optional[float],
    year_built: Optional[int],
    sqft: Optional[int],
) -> tuple:
    """
    Estimate deal equity from available property data.

    Returns (equity_confidence, mao, repair_est) where:
      equity_confidence: "high" | "medium" | "low" | "dead" | "unknown"
      mao:               float or None
      repair_est:        float or None
    """
    if not assessed_value:
        return "unknown", None, None

    sqft_eff    = sqft or DEFAULT_SQFT
    repair_rate = REPAIR_RATE_OLD if (year_built and year_built < 1980) else REPAIR_RATE_NEW
    repair_est  = sqft_eff * repair_rate

    estimated_arv = assessed_value * ARV_UPLIFT
    mao           = estimated_arv * MAO_FACTOR - repair_est

    if mao <= 0:
        return "dead", mao, repair_est
    if mao > assessed_value * 0.50:
        return "high", mao, repair_est
    if mao > assessed_value * 0.25:
        return "medium", mao, repair_est
    return "low", mao, repair_est


def _compute_lead_score(
    intent: str,
    equity_conf: str,
    urgency: int,
    has_phone: bool,
    mao: Optional[float],
) -> str:
    """Core scoring matrix — returns raw score before priority zip boost."""
    # Negative equity or hard stop → always dead
    if equity_conf == "dead" or (mao is not None and mao <= 0):
        return "dead"
    if intent == "NOT_INTERESTED_HARD":
        return "dead"

    if intent == "INTERESTED":
        if equity_conf in ("high", "medium"):
            if has_phone:
                return "hot"
            # No phone: hot only if very urgent, else warm
            return "hot" if urgency >= 4 else "warm"
        # Low or unknown equity + interested → warm
        return "warm"

    if intent == "NOT_INTERESTED_SOFT":
        return "cold"  # one last shot possible, but never upgrades beyond cold

    if intent == "NEEDS_FOLLOWUP":
        if equity_conf in ("high", "medium") and urgency >= 3 and has_phone:
            return "warm"
        return "cold"

    # NO_REPLY
    if equity_conf in ("high", "medium") and urgency >= 4 and has_phone:
        return "warm"
    return "cold"


def _apply_priority_boost(score: str, is_priority: bool) -> str:
    """Upgrade score one level for priority zip codes. Never upgrades dead."""
    if not is_priority or score == "dead":
        return score
    boosted = min(_SCORE_RANK[score] + 1, _SCORE_RANK["hot"])
    return _RANK_SCORE[boosted]


def _recommended_action(
    score: str,
    intent: str,
    has_phone: bool,
    first_name: str,
    seller_name: str,
    days_left: Optional[int],
    mao: Optional[float],
) -> str:
    days_str = f"{days_left} days" if (days_left is not None and days_left > 0) else "soon"

    if score == "hot":
        if has_phone:
            return f"Call {first_name} NOW — ask for a 10-min walkthrough"
        return f"Skip trace {seller_name} immediately, then call"

    if score == "warm":
        if intent == "INTERESTED":
            return "Follow up SMS within 24 hours, offer a specific time to talk"
        if not has_phone:
            return f"Skip trace {seller_name} immediately"
        return f"Send second SMS today — auction in {days_str}"

    if score == "cold":
        if intent == "NOT_INTERESTED_SOFT":
            return "One last SMS attempt, then archive if still no response"
        return "One more SMS in 3 days, then archive if no response"

    # dead
    if mao is not None and mao <= 0:
        return "Archive standard; flag for subject-to research"
    return "Archive — note as no-equity for future list cleaning"


def _build_questions(
    intent: str,
    year_built: Optional[int],
    assessed_value: Optional[float],
) -> list:
    qs = [
        "Are you currently living at the property or is it vacant?",
        "Are you still current on the mortgage, or are there any other liens?",
    ]
    if year_built and year_built < 1980:
        qs.append(
            "Have there been any major repairs done recently — roof, plumbing, electrical?"
        )
    if intent == "INTERESTED":
        qs.append("What would a fair offer look like for you?")
        qs.append("When could we do a quick 10-minute walkthrough?")
    if not assessed_value:
        qs.append(
            "Do you know roughly what the property is worth or what you owe on it?"
        )
    return qs


def _build_notes(
    intent: str,
    year_built: Optional[int],
    mao: Optional[float],
    assessed_value: Optional[float],
    repair_est: Optional[float],
    equity_conf: str,
    seller_reply: str,
    is_priority: bool,
    has_phone: bool,
) -> list:
    notes = []

    if year_built and year_built < 1980:
        notes.append(
            f"Pre-1980 build ({year_built}): elevated repair risk — "
            "cast iron pipes, old electrical, possible foundation issues. "
            "Using $20/sqft repair estimate."
        )

    if intent == "INTERESTED" and seller_reply:
        snippet = str(seller_reply)[:120].replace('"', "'")
        notes.append(f'Seller said: "{snippet}" — classified INTERESTED')
    elif intent == "NOT_INTERESTED_HARD":
        notes.append("Seller sent hard stop — do not contact again")
    elif intent == "NOT_INTERESTED_SOFT":
        notes.append("Seller declined softly — one more attempt may be appropriate")

    if assessed_value and mao is not None and repair_est is not None:
        notes.append(
            f"Estimated MAO: ${mao:,.0f} "
            f"(ARV ${assessed_value * ARV_UPLIFT:,.0f}, repairs ${repair_est:,.0f})"
        )

    if equity_conf == "dead" and mao is not None and mao <= 0:
        notes.append(
            "Owes more than ARV minus repairs — no equity for standard wholesale"
        )
        if assessed_value:
            notes.append(
                "Creative option: subject-to or short sale if seller is motivated"
            )

    if is_priority:
        notes.append("Priority zip — inner loop appreciation zone")

    if not has_phone:
        notes.append("Added to skip trace queue")

    return notes


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_lead(
    property_address: str,
    seller_name: str,
    sale_date: str,
    phone: str,
    assessed_value: Optional[float],
    year_built: Optional[int],
    sqft: Optional[int],
    seller_reply: str,
    run_date: date = None,
) -> dict:
    """
    Score a single lead. All inputs except property_address are optional.
    Returns a dict with all spec output fields.
    """
    _name_parts = (seller_name or "").split()
    first_name  = _name_parts[0] if _name_parts else "Seller"
    has_phone   = bool(phone and str(phone).strip())
    reply       = str(seller_reply or "").strip()

    urgency     = urgency_score(sale_date, run_date)
    days_left   = _days_until(sale_date, run_date)
    intent      = classify_intent(reply)
    equity_conf, mao, repair_est = estimate_equity(assessed_value, year_built, sqft)
    is_priority = _extract_zip(property_address or "") in PRIORITY_ZIPS

    raw_score   = _compute_lead_score(intent, equity_conf, urgency, has_phone, mao)
    final_score = _apply_priority_boost(raw_score, is_priority)

    offer_needed = final_score == "hot" and equity_conf in ("high", "medium")

    action    = _recommended_action(
        final_score, intent, has_phone,
        first_name, seller_name or "Seller", days_left, mao,
    )
    questions = _build_questions(intent, year_built, assessed_value)
    notes     = _build_notes(
        intent, year_built, mao, assessed_value, repair_est,
        equity_conf, reply, is_priority, has_phone,
    )

    # Map internal "dead" equity state → "low" for output
    # (equity_confidence output values: high/medium/low/unknown per spec §3)
    out_equity = "low" if equity_conf == "dead" else equity_conf

    return {
        "property_address":        property_address or "",
        "seller_name":             seller_name or "",
        "sale_date":               sale_date or "",
        "phone":                   phone or "",
        "assessed_value":          assessed_value,
        "year_built":              year_built,
        "sqft":                    sqft,
        "seller_reply":            seller_reply or "",
        "lead_score":              final_score,
        "urgency_score":           urgency,
        "equity_confidence":       out_equity,
        "recommended_next_action": action,
        "questions_to_ask_seller": questions,
        "offer_needed":            offer_needed,
        "notes":                   notes,
    }


# ---------------------------------------------------------------------------
# CSV batch processing
# ---------------------------------------------------------------------------

def _resolve_field(row: dict, field: str, known_headers: set) -> str:
    """Return first non-empty value from the alias list for this field."""
    for alias in _COLUMN_ALIASES[field]:
        if alias in known_headers:
            val = str(row.get(alias, "")).strip()
            if val:
                return val
    return ""


def _to_float(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(re.sub(r"[,$]", "", s).strip())
    except ValueError:
        return None


def _to_int(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        return int(float(re.sub(r"[,$]", "", s).strip()))
    except ValueError:
        return None


def process_csv(
    input_path: str,
    output_csv:     str = None,
    output_json:    str = None,
    skip_trace_csv: str = "skip_trace_queue.csv",
    run_date:       date = None,
) -> list:
    """
    Process a CSV of leads and return list of scored dicts.
    Writes output_csv, output_json, and skip_trace_csv as side effects.
    """
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader   = csv.DictReader(f)
        raw_rows = list(reader)
        original_fieldnames = list(reader.fieldnames or [])

    known_headers = {h.strip() for h in original_fieldnames}
    scored_results = []
    output_rows    = []
    skip_trace_rows = []

    for row in raw_rows:
        addr   = _resolve_field(row, "property_address", known_headers)
        name   = _resolve_field(row, "seller_name",      known_headers)
        sdate  = _resolve_field(row, "sale_date",        known_headers)
        phone  = _resolve_field(row, "phone",            known_headers)
        aval   = _to_float(_resolve_field(row, "assessed_value", known_headers))
        ybuilt = _to_int(_resolve_field(row,   "year_built",     known_headers))
        sq     = _to_int(_resolve_field(row,   "sqft",           known_headers))
        reply  = _resolve_field(row, "seller_reply",     known_headers)

        scored = score_lead(
            property_address=addr,
            seller_name=name,
            sale_date=sdate,
            phone=phone,
            assessed_value=aval,
            year_built=ybuilt,
            sqft=sq,
            seller_reply=reply,
            run_date=run_date,
        )

        # Preserve all original columns + append scored columns
        out_row = {k.strip(): v for k, v in row.items()}
        out_row["lead_score"]              = scored["lead_score"]
        out_row["urgency_score"]           = scored["urgency_score"]
        out_row["equity_confidence"]       = scored["equity_confidence"]
        out_row["recommended_next_action"] = scored["recommended_next_action"]
        out_row["questions_to_ask_seller"] = "|".join(scored["questions_to_ask_seller"])
        out_row["offer_needed"]            = "yes" if scored["offer_needed"] else "no"
        out_row["notes"]                   = "|".join(scored["notes"])

        scored_results.append(scored)
        output_rows.append(out_row)

        if not phone.strip():
            skip_trace_rows.append({
                "seller_name":      name,
                "property_address": addr,
                "sale_date":        sdate,
                "lead_score":       scored["lead_score"],
                "urgency_score":    scored["urgency_score"],
            })

    # Sort: hot→warm→cold→dead, then urgency descending
    def _sort_key(row_dict):
        return (
            _SCORE_RANK.get(row_dict["lead_score"], 0),
            row_dict["urgency_score"],
        )

    output_rows    = sorted(output_rows,    key=_sort_key, reverse=True)
    scored_results = sorted(scored_results, key=_sort_key, reverse=True)

    # Write CSV
    if output_csv and output_rows:
        scored_fields = [
            "lead_score", "urgency_score", "equity_confidence",
            "recommended_next_action", "questions_to_ask_seller",
            "offer_needed", "notes",
        ]
        all_fields = original_fieldnames + scored_fields
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(output_rows)

    # Write JSON
    if output_json and scored_results:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(scored_results, f, indent=2, default=str)

    # Write skip trace queue
    if skip_trace_rows and skip_trace_csv:
        with open(skip_trace_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["seller_name","property_address","sale_date",
                               "lead_score","urgency_score"]
            )
            writer.writeheader()
            writer.writerows(skip_trace_rows)

    return scored_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_table(results: list) -> None:
    """Pretty-print scored results to stdout."""
    SCORE_ICON = {"hot": "*** HOT", "warm": " ** WARM", "cold": "  * COLD", "dead": "    DEAD"}

    print()
    print(f"{'SCORE':<10} {'URG':>3}  {'EQUITY':<8}  {'OFFER':>5}  {'NAME':<18}  {'ADDRESS':<35}  ACTION")
    print("-" * 120)
    for r in results:
        icon   = SCORE_ICON.get(r["lead_score"], r["lead_score"].upper())
        name   = (r["seller_name"] or "")[:18]
        addr   = (r["property_address"] or "")[:35]
        action = r["recommended_next_action"][:55]
        offer  = "YES" if r["offer_needed"] else "no"
        print(f"{icon:<10} {r['urgency_score']:>3}  {r['equity_confidence']:<8}  {offer:>5}  {name:<18}  {addr:<35}  {action}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Rule-based deal intelligence scoring for Houston wholesale leads"
    )

    # Batch mode
    parser.add_argument("--input",       help="Input CSV file path")
    parser.add_argument("--output",      help="Output CSV file path")
    parser.add_argument("--json",        help="Output JSON file path")
    parser.add_argument("--skip-trace",  default="skip_trace_queue.csv",
                        help="Skip trace queue CSV (default: skip_trace_queue.csv)")

    # Single record mode
    parser.add_argument("--address",        help="Property address")
    parser.add_argument("--seller",         help="Seller name")
    parser.add_argument("--sale-date",      help="Sale date (YYYY-MM-DD)")
    parser.add_argument("--phone",          help="Phone number")
    parser.add_argument("--assessed-value", type=float, help="HCAD assessed value")
    parser.add_argument("--year-built",     type=int,   help="Year built")
    parser.add_argument("--sqft",           type=int,   help="Square footage")
    parser.add_argument("--reply",          help="Seller's SMS reply text")

    args = parser.parse_args()

    if args.input:
        # Batch mode
        print(f"Scoring {args.input}...")
        results = process_csv(
            input_path=args.input,
            output_csv=args.output,
            output_json=args.json,
            skip_trace_csv=args.skip_trace,
        )
        _print_table(results)

        if args.output:
            print(f"CSV  -> {args.output}")
        if args.json:
            print(f"JSON -> {args.json}")
        print(f"Skip trace queue -> {args.skip_trace}")
        print(f"\nTotal: {len(results)}  |  "
              f"Hot: {sum(1 for r in results if r['lead_score']=='hot')}  "
              f"Warm: {sum(1 for r in results if r['lead_score']=='warm')}  "
              f"Cold: {sum(1 for r in results if r['lead_score']=='cold')}  "
              f"Dead: {sum(1 for r in results if r['lead_score']=='dead')}")

    elif args.address:
        # Single record mode
        result = score_lead(
            property_address=args.address,
            seller_name=args.seller or "",
            sale_date=args.sale_date or "",
            phone=args.phone or "",
            assessed_value=args.assessed_value,
            year_built=args.year_built,
            sqft=args.sqft,
            seller_reply=args.reply or "",
        )
        print(json.dumps(result, indent=2, default=str))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
