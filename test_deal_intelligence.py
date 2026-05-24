"""
test_deal_intelligence.py -- Unit tests for deal_intelligence.py

Run with:
    pytest test_deal_intelligence.py -v
"""

import os
import csv
import tempfile
import pytest
from datetime import date

from deal_intelligence import (
    urgency_score,
    classify_intent,
    estimate_equity,
    score_lead,
    _extract_zip,
    _apply_priority_boost,
    _compute_lead_score,
    process_csv,
    REPAIR_RATE_OLD,
    REPAIR_RATE_NEW,
    ARV_UPLIFT,
    MAO_FACTOR,
)

# Fixed reference date for all tests — makes urgency deterministic
FIXED = date(2026, 6, 1)


# ===========================================================================
# AC-1: Urgency scoring
# ===========================================================================

def test_urgency_5():
    """5 days to auction → urgency 5"""
    assert urgency_score("2026-06-06", FIXED) == 5

def test_urgency_4():
    """11 days to auction → urgency 4"""
    assert urgency_score("2026-06-12", FIXED) == 4

def test_urgency_3():
    """20 days to auction → urgency 3"""
    assert urgency_score("2026-06-21", FIXED) == 3

def test_urgency_2():
    """44 days to auction → urgency 2"""
    assert urgency_score("2026-07-15", FIXED) == 2

def test_urgency_1_far():
    """92 days to auction → urgency 1"""
    assert urgency_score("2026-09-01", FIXED) == 1

def test_urgency_1_past():
    """Past date → urgency 1"""
    assert urgency_score("2026-05-01", FIXED) == 1

def test_urgency_1_none():
    """Missing date → urgency 1"""
    assert urgency_score("", FIXED) == 1

def test_urgency_1_unparseable():
    """Garbage date string → urgency 1"""
    assert urgency_score("not-a-date", FIXED) == 1

def test_urgency_boundary_7():
    """Exactly 7 days → urgency 5 (boundary)"""
    assert urgency_score("2026-06-08", FIXED) == 5

def test_urgency_boundary_8():
    """Exactly 8 days → urgency 4 (boundary)"""
    assert urgency_score("2026-06-09", FIXED) == 4


# ===========================================================================
# AC-2: Seller intent classification
# ===========================================================================

def test_intent_how_much():
    assert classify_intent("how much are you offering") == "INTERESTED"

def test_intent_yes():
    assert classify_intent("yes I'd be interested") == "INTERESTED"

def test_intent_yeah():
    assert classify_intent("yeah give me a call") == "INTERESTED"

def test_intent_maybe():
    """'I might consider it' contains 'might consider' phrase"""
    assert classify_intent("I might consider it") == "INTERESTED"

def test_intent_sure():
    assert classify_intent("sure, what's the offer?") == "INTERESTED"

def test_intent_case_insensitive():
    assert classify_intent("YES CALL ME") == "INTERESTED"

def test_intent_no_thanks():
    assert classify_intent("no thanks") == "NOT_INTERESTED_SOFT"

def test_intent_not_interested():
    assert classify_intent("I'm not interested") == "NOT_INTERESTED_SOFT"

def test_intent_have_agent():
    assert classify_intent("I already have an agent") == "NOT_INTERESTED_SOFT"

def test_intent_already_sold():
    assert classify_intent("already sold, thanks") == "NOT_INTERESTED_SOFT"

def test_intent_hard_stop_phrase():
    assert classify_intent("stop texting me") == "NOT_INTERESTED_HARD"

def test_intent_hard_stop_bare():
    """Single word 'stop' = TCPA opt-out"""
    assert classify_intent("STOP") == "NOT_INTERESTED_HARD"

def test_intent_dont_contact():
    assert classify_intent("please don't contact me again") == "NOT_INTERESTED_HARD"

def test_intent_empty():
    assert classify_intent("") == "NO_REPLY"

def test_intent_none():
    assert classify_intent(None) == "NO_REPLY"

def test_intent_whitespace():
    assert classify_intent("   ") == "NO_REPLY"

def test_intent_needs_followup():
    assert classify_intent("what do you mean exactly?") == "NEEDS_FOLLOWUP"

def test_intent_needs_followup_question():
    assert classify_intent("who is this?") == "NEEDS_FOLLOWUP"


# ===========================================================================
# Equity estimation (used in AC-3, AC-4, AC-7, AC-8)
# ===========================================================================

def test_equity_high():
    """assessed=200k, sqft=1200, post-1980 → high"""
    # mao = 200000*1.10*0.70 - 18000 = 136000 > 200000*0.50 = 100000
    conf, mao, repairs = estimate_equity(200000, 1990, 1200)
    assert conf == "high"
    assert mao == pytest.approx(136000)
    assert repairs == 1200 * REPAIR_RATE_NEW

def test_equity_medium():
    """assessed=50k, sqft=1200, post-1980 → medium"""
    # mao = 50000*1.10*0.70 - 18000 = 20500
    # 20500 > 50000*0.25=12500 but not > 50000*0.50=25000 → medium
    conf, mao, _ = estimate_equity(50000, 1990, 1200)
    assert conf == "medium"
    assert mao > 0

def test_equity_low():
    """assessed=50k, sqft=2000, post-1980 → low"""
    # mao = 38500 - 30000 = 8500 → > 0 but ≤ 12500 → low
    conf, mao, _ = estimate_equity(50000, 1990, 2000)
    assert conf == "low"
    assert mao > 0

def test_equity_dead():
    """assessed=50k, sqft=3000, post-1980 → mao negative → dead"""
    # mao = 38500 - 45000 = -6500
    conf, mao, _ = estimate_equity(50000, 1990, 3000)
    assert conf == "dead"
    assert mao is not None and mao <= 0

def test_equity_unknown():
    """No assessed value → unknown"""
    conf, mao, repairs = estimate_equity(None, 1990, 1200)
    assert conf == "unknown"
    assert mao is None
    assert repairs is None


# ===========================================================================
# AC-3: Lead scoring
# ===========================================================================

def test_hot_full():
    """INTERESTED + high equity + phone → hot"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   200000, 1990, 1200, "yes I'm interested", FIXED)
    assert r["lead_score"] == "hot"

def test_hot_no_phone_urgent():
    """INTERESTED + high equity + no phone + urgency 5 → hot (urgent enough)"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "",           # no phone, urgency 5
                   200000, 1990, 1200, "yes I'm interested", FIXED)
    assert r["lead_score"] == "hot"
    assert "skip trace" in r["recommended_next_action"].lower()

def test_warm_interested_no_phone_low_urgency():
    """INTERESTED + high equity + no phone + urgency 2 → warm"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-07-15", "",           # no phone, urgency 2
                   200000, 1990, 1200, "yes I'm interested", FIXED)
    assert r["lead_score"] == "warm"

def test_warm_low_equity():
    """INTERESTED + low equity → warm regardless of phone/urgency"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 2000,          # low equity
                   "yes I'm interested", FIXED)
    assert r["lead_score"] == "warm"

def test_warm_needs_followup_high_equity():
    """NEEDS_FOLLOWUP + high equity + urgency 3 + phone → warm"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-21", "+17135551234",   # urgency 3
                   200000, 1990, 1200, "what do you mean?", FIXED)
    assert r["lead_score"] == "warm"

def test_warm_no_reply_high_equity_urgent():
    """NO_REPLY + high equity + urgency 4 + phone → warm"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-09", "+17135551234",   # urgency 4
                   200000, 1990, 1200, "", FIXED)
    assert r["lead_score"] == "warm"

def test_cold_no_reply_unknown_equity():
    """NO_REPLY + no assessed value → cold"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   None, None, None, "", FIXED)
    assert r["lead_score"] == "cold"

def test_cold_soft_no():
    """NOT_INTERESTED_SOFT → always cold"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   200000, 1990, 1200, "not interested", FIXED)
    assert r["lead_score"] == "cold"

def test_dead_negative_mao():
    """mao <= 0 → dead, even with INTERESTED reply"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000,           # dead equity
                   "yes I'm interested", FIXED)
    assert r["lead_score"] == "dead"

def test_dead_hard_stop():
    """Hard stop → dead regardless of equity"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   200000, 1990, 1200, "stop texting me", FIXED)
    assert r["lead_score"] == "dead"


# ===========================================================================
# AC-4: Pre-1980 repair flag
# ===========================================================================

def test_pre1980_repair_rate():
    """year_built=1975 → uses $20/sqft repair rate"""
    _, _, repair_est = estimate_equity(142000, 1975, 1350)
    assert repair_est == 1350 * REPAIR_RATE_OLD      # $27,000

def test_pre1980_note_present():
    """year_built=1975 → notes contains 'Pre-1980' string"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   142000, 1975, 1350, "", FIXED)
    assert any("Pre-1980" in n for n in r["notes"])

def test_post1980_repair_rate():
    """year_built=1985 → uses $15/sqft repair rate"""
    _, _, repair_est = estimate_equity(142000, 1985, 1350)
    assert repair_est == 1350 * REPAIR_RATE_NEW      # $20,250

def test_post1980_no_flag():
    """year_built=1985 → no pre-1980 note"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   142000, 1985, 1350, "", FIXED)
    assert not any("Pre-1980" in n for n in r["notes"])


# ===========================================================================
# AC-5: Priority zip upgrade
# ===========================================================================

def test_priority_zip_cold_to_warm():
    """cold lead in 77003 → upgraded to warm"""
    r = score_lead("123 MAIN ST HOUSTON TX 77003", "JOHN DOE",
                   "", "+17135551234",   # urgency 1
                   None, None, None, "", FIXED)
    # Without zip boost: cold.  With 77003: warm
    assert r["lead_score"] == "warm"

def test_priority_zip_warm_to_hot():
    """warm lead in 77011 → upgraded to hot"""
    # INTERESTED + low equity → warm, then +1 for 77011 → hot
    r = score_lead("456 OAK ST HOUSTON TX 77011", "JANE DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 2000,   # low equity → warm if INTERESTED
                   "yes I'm interested", FIXED)
    assert r["lead_score"] == "hot"

def test_priority_zip_77023():
    """cold lead in 77023 → upgraded to warm"""
    r = score_lead("789 ELM ST HOUSTON TX 77023", "JOHN DOE",
                   "", "+17135551234",
                   None, None, None, "", FIXED)
    assert r["lead_score"] == "warm"

def test_nonpriority_zip_no_change():
    """cold lead in 77084 → stays cold"""
    r = score_lead("100 MAIN ST HOUSTON TX 77084", "JOHN DOE",
                   "", "+17135551234",
                   None, None, None, "", FIXED)
    assert r["lead_score"] == "cold"

def test_priority_zip_no_dead_upgrade():
    """dead lead in 77003 → stays dead (never upgrade dead)"""
    r = score_lead("100 MAIN ST HOUSTON TX 77003", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000,   # dead equity
                   "yes I'm interested", FIXED)
    assert r["lead_score"] == "dead"

def test_apply_priority_boost_unit():
    """Unit test _apply_priority_boost directly"""
    assert _apply_priority_boost("cold", True)  == "warm"
    assert _apply_priority_boost("warm", True)  == "hot"
    assert _apply_priority_boost("hot",  True)  == "hot"   # already max
    assert _apply_priority_boost("dead", True)  == "dead"  # never boost dead
    assert _apply_priority_boost("cold", False) == "cold"  # no boost


# ===========================================================================
# AC-6: No-phone handling
# ===========================================================================

def test_no_phone_action_contains_skip_trace():
    """No phone → recommended_next_action mentions skip trace"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "",
                   200000, 1990, 1200, "yes I'm interested", FIXED)
    assert "skip trace" in r["recommended_next_action"].lower()

def test_no_phone_note_added():
    """No phone → notes includes skip trace queue message"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "",
                   None, None, None, "", FIXED)
    assert any("skip trace queue" in n.lower() for n in r["notes"])

def test_no_phone_hot_still_hot():
    """INTERESTED + high equity + urgency 5 + no phone → still hot"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "",
                   200000, 1990, 1200, "yes", FIXED)
    assert r["lead_score"] == "hot"


# ===========================================================================
# AC-7: offer_needed flag
# ===========================================================================

def test_offer_needed_hot_high():
    """hot + high equity → offer_needed True"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   200000, 1990, 1200, "yes I'm interested", FIXED)
    assert r["offer_needed"] is True

def test_offer_needed_hot_medium():
    """hot + medium equity → offer_needed True"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 1200,   # medium equity
                   "yes I'm interested", FIXED)
    assert r["offer_needed"] is True

def test_offer_needed_warm_false():
    """warm lead → offer_needed False"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 2000,   # low equity → warm
                   "yes I'm interested", FIXED)
    assert r["offer_needed"] is False

def test_offer_needed_dead_false():
    """dead lead → offer_needed False"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000,   # dead equity
                   "yes I'm interested", FIXED)
    assert r["offer_needed"] is False


# ===========================================================================
# AC-8: Dead deal creative financing flag
# ===========================================================================

def test_creative_flag_present():
    """mao <= 0 + assessed_value present → notes has creative option"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000, "", FIXED)
    assert any("creative option" in n.lower() for n in r["notes"])
    assert any("subject-to" in n.lower() for n in r["notes"])

def test_negative_equity_no_equity_note():
    """mao <= 0 → notes has 'no equity' message"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000, "", FIXED)
    assert any("no equity" in n.lower() for n in r["notes"])

def test_equity_confidence_dead_maps_to_low():
    """Internal 'dead' equity maps to 'low' in output equity_confidence"""
    r = score_lead("100 MAIN ST HOUSTON TX 77050", "JOHN DOE",
                   "2026-06-06", "+17135551234",
                   50000, 1990, 3000, "", FIXED)
    assert r["equity_confidence"] == "low"   # "dead" is internal only
    assert r["lead_score"] == "dead"         # lead_score still shows dead


# ===========================================================================
# AC-9: Output format / robustness
# ===========================================================================

def test_output_has_all_required_keys():
    """All 7 output keys present in every result"""
    r = score_lead("100 MAIN ST", "JOHN", "", "", None, None, None, "", FIXED)
    for key in ["lead_score","urgency_score","equity_confidence",
                "recommended_next_action","questions_to_ask_seller",
                "offer_needed","notes"]:
        assert key in r, f"Missing key: {key}"

def test_missing_optional_fields_no_crash():
    """All optional fields None/empty → no exception"""
    r = score_lead("100 MAIN ST", "", "", "", None, None, None, "", FIXED)
    assert r["lead_score"] in ("hot","warm","cold","dead")

def test_questions_is_list():
    r = score_lead("100 MAIN ST", "JOE", "", "+17135551234", None, None, None, "", FIXED)
    assert isinstance(r["questions_to_ask_seller"], list)
    assert len(r["questions_to_ask_seller"]) >= 2

def test_notes_is_list():
    r = score_lead("100 MAIN ST", "JOE", "", "+17135551234", None, None, None, "", FIXED)
    assert isinstance(r["notes"], list)

def test_deterministic():
    """Same input twice → identical output"""
    kwargs = dict(
        property_address="3927 CYPRESS HILL DR HOUSTON TX 77084",
        seller_name="JESSIE LEE",
        sale_date="2026-06-03",
        phone="+12137332966",
        assessed_value=142000,
        year_built=1978,
        sqft=1350,
        seller_reply="how much are you offering",
        run_date=FIXED,
    )
    r1 = score_lead(**kwargs)
    r2 = score_lead(**kwargs)
    assert r1 == r2

def test_equity_confidence_valid_values():
    """equity_confidence output is always one of the 4 spec values"""
    valid = {"high", "medium", "low", "unknown"}
    for assessed, sqft in [(200000, 1200), (50000, 1200), (50000, 2000),
                           (50000, 3000), (None, 1200)]:
        r = score_lead("100 MAIN ST", "JOE", "", "+1234567890",
                       assessed, 1990, sqft, "", FIXED)
        assert r["equity_confidence"] in valid, \
            f"Invalid equity_confidence '{r['equity_confidence']}' for assessed={assessed}, sqft={sqft}"

def test_lead_score_valid_values():
    valid = {"hot", "warm", "cold", "dead"}
    r = score_lead("100 MAIN ST", "JOE", "", "+1234567890",
                   200000, 1990, 1200, "yes", FIXED)
    assert r["lead_score"] in valid


# ===========================================================================
# AC-6 (extra): Skip trace queue written to CSV
# ===========================================================================

def test_skip_trace_queue_written(tmp_path):
    """Rows with no phone → written to skip_trace_queue.csv"""
    input_csv = tmp_path / "leads.csv"
    output_csv = tmp_path / "scored.csv"
    skip_csv   = tmp_path / "skip.csv"

    # Write a mini CSV with one row, no phone
    input_csv.write_text(
        "property_address,seller_name,sale_date,phone,assessed_value,year_built,sqft,seller_reply\n"
        '\"100 MAIN ST HOUSTON TX 77050\",JOHN DOE,2026-06-06,,200000,1990,1200,\n',
        encoding="utf-8"
    )

    process_csv(
        str(input_csv),
        output_csv=str(output_csv),
        skip_trace_csv=str(skip_csv),
        run_date=FIXED,
    )

    assert skip_csv.exists()
    rows = list(csv.DictReader(skip_csv.open(newline="")))
    assert len(rows) == 1
    assert rows[0]["seller_name"] == "JOHN DOE"


def test_csv_roundtrip_preserves_input_cols(tmp_path):
    """All original CSV columns are preserved in output"""
    input_csv  = tmp_path / "leads.csv"
    output_csv = tmp_path / "scored.csv"

    input_csv.write_text(
        "property_address,seller_name,sale_date,phone,assessed_value,year_built,sqft,seller_reply\n"
        '\"100 MAIN ST HOUSTON TX 77050\",JOHN DOE,2026-06-06,+17135551234,200000,1990,1200,\n',
        encoding="utf-8"
    )

    process_csv(str(input_csv), output_csv=str(output_csv), run_date=FIXED)

    rows = list(csv.DictReader(output_csv.open(newline="")))
    assert len(rows) == 1
    # Original columns preserved
    assert rows[0]["property_address"] == "100 MAIN ST HOUSTON TX 77050"
    assert rows[0]["seller_name"]      == "JOHN DOE"
    # Scored columns added
    assert rows[0]["lead_score"]       in ("hot","warm","cold","dead")
    assert rows[0]["offer_needed"]     in ("yes","no")


def test_csv_questions_pipe_delimited(tmp_path):
    """questions_to_ask_seller in CSV output is pipe-delimited"""
    input_csv  = tmp_path / "leads.csv"
    output_csv = tmp_path / "scored.csv"

    input_csv.write_text(
        "property_address,seller_name,sale_date,phone,assessed_value,year_built,sqft,seller_reply\n"
        '\"100 MAIN ST HOUSTON TX 77050\",JOHN DOE,2026-06-06,+17135551234,200000,1990,1200,yes\n',
        encoding="utf-8"
    )

    process_csv(str(input_csv), output_csv=str(output_csv), run_date=FIXED)

    rows = list(csv.DictReader(output_csv.open(newline="")))
    assert "|" in rows[0]["questions_to_ask_seller"]


def test_column_aliasing(tmp_path):
    """CSV with 'street' and 'first_name' columns are aliased correctly"""
    input_csv  = tmp_path / "leads.csv"
    output_csv = tmp_path / "scored.csv"

    # Uses 'street' (not 'property_address') and 'first_name' (not 'seller_name')
    input_csv.write_text(
        "phone,first_name,street\n"
        '+17135551234,JOHN,\"100 MAIN ST HOUSTON TX 77050\"\n',
        encoding="utf-8"
    )

    results = process_csv(str(input_csv), output_csv=str(output_csv), run_date=FIXED)
    assert len(results) == 1
    assert results[0]["seller_name"] == "JOHN"
    assert results[0]["property_address"] == "100 MAIN ST HOUSTON TX 77050"


# ===========================================================================
# MAO calculation sanity check
# ===========================================================================

def test_mao_formula_correct():
    """MAO = ARV * 0.70 - repairs matches formula exactly"""
    assessed = 142000
    sqft     = 1350
    year     = 1978  # pre-1980

    expected_repairs = sqft * 20               # REPAIR_RATE_OLD
    expected_arv     = assessed * ARV_UPLIFT
    expected_mao     = expected_arv * MAO_FACTOR - expected_repairs

    _, mao, repairs = estimate_equity(assessed, year, sqft)
    assert repairs == pytest.approx(expected_repairs)
    assert mao     == pytest.approx(expected_mao)


def test_extract_zip():
    assert _extract_zip("3927 CYPRESS HILL DR HOUSTON TX 77084") == "77084"
    assert _extract_zip("100 MAIN ST")                           == ""
    assert _extract_zip("")                                      == ""
    assert _extract_zip(None)                                    == ""
