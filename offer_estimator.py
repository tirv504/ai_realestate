"""
offer_estimator.py -- MAO calculator + AI explanation for Houston wholesaling

Usage (ARV already known — fastest):
    python offer_estimator.py "4510 KINGLET ST HOUSTON TX 77035" --arv 185000
    python offer_estimator.py "4510 KINGLET ST HOUSTON TX 77035" --arv 185000 --repairs 25000

Usage (interactive prompt for ARV):
    python offer_estimator.py "4510 KINGLET ST HOUSTON TX 77035"

Tip: Look up HCAD value at https://search.hcad.org/ and pass it with --arv.
"""

import os
import sys
import argparse
import anthropic

MAO_FACTOR        = 0.70
DEFAULT_REPAIRS   = 20_000
TARGET_ASSIGN_FEE = 10_000


# -- MAO calculator ------------------------------------------------------------

def calculate_mao(arv: float, repairs: float) -> dict:
    mao        = arv * MAO_FACTOR - repairs
    your_offer = mao - TARGET_ASSIGN_FEE
    offer_low  = your_offer - 5_000
    offer_high = your_offer

    return {
        "arv":         arv,
        "mao":         mao,
        "repairs":     repairs,
        "offer_low":   max(offer_low, 0),
        "offer_high":  max(offer_high, 0),
        "assign_room": mao - your_offer,
    }


# -- AI explanation ------------------------------------------------------------

def get_explanation(address: str, arv: float, calc: dict, meta: dict) -> str:
    key    = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return "(Set ANTHROPIC_API_KEY env var to enable AI breakdown.)"

    client = anthropic.Anthropic(api_key=key)

    context = (
        f"Property: {address}\n"
        f"HCAD Appraised Value (used as ARV): ${arv:,.0f}\n"
        f"Estimated Repairs: ${calc['repairs']:,.0f}\n"
        f"ARV x 70% = ${arv * MAO_FACTOR:,.0f}\n"
        f"MAO (ARV x 70% - repairs): ${calc['mao']:,.0f}\n"
        f"Recommended Offer Range: ${calc['offer_low']:,.0f} - ${calc['offer_high']:,.0f}\n"
        f"Assignment Fee Room: ${calc['assign_room']:,.0f}\n"
    )
    if meta.get("sqft"):
        context += f"Size: {meta['sqft']:,} sq ft\n"
    if meta.get("year_built"):
        context += f"Year Built: {meta['year_built']}\n"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=(
            "You are a real estate wholesaling coach. "
            "Given the property data below, explain the offer in plain English in 3-4 sentences. "
            "Cover: what the property is worth, why the offer is where it is, "
            "what risks exist, and what the wholesaler stands to make. Be direct and practical."
        ),
        messages=[{"role": "user", "content": context}],
    )
    return response.content[0].text.strip()


# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="MAO calculator for Houston wholesale deals"
    )
    parser.add_argument("address",         help="Property address")
    parser.add_argument("--arv",    type=float, default=None,
                        help="HCAD appraised value / ARV (skips lookup prompt)")
    parser.add_argument("--repairs", type=float, default=DEFAULT_REPAIRS,
                        help=f"Estimated repair cost (default ${DEFAULT_REPAIRS:,})")
    parser.add_argument("--sqft",   type=int,   default=None, help="Square footage")
    parser.add_argument("--year",   type=int,   default=None, help="Year built")
    args = parser.parse_args()

    address = args.address
    repairs = args.repairs
    meta    = {}

    print(f"\nProperty : {address}")
    print("-" * 60)

    arv = args.arv

    if not arv:
        print("Tip: look up this address at https://search.hcad.org/")
        print("     and pass the appraised value with --arv VALUE")
        print()
        raw = input("Enter HCAD Appraised Value (e.g. 185000): $").strip()
        try:
            arv = float(raw.replace(",", "").replace("$", ""))
        except ValueError:
            print("Invalid number. Exiting.")
            sys.exit(1)

    if args.sqft:
        meta["sqft"] = args.sqft
    if args.year:
        meta["year_built"] = args.year

    calc = calculate_mao(arv, repairs)

    print(f"\n  HCAD Value    : ${arv:,.0f}")
    print(f"  Est. Repairs  : ${repairs:,.0f}")
    print(f"  ARV x 70%     : ${arv * MAO_FACTOR:,.0f}")
    print(f"  MAO           : ${calc['mao']:,.0f}")
    print(f"\n  >> Offer Range: ${calc['offer_low']:,.0f} - ${calc['offer_high']:,.0f}")
    print(f"  Assignment $  : ~${calc['assign_room']:,.0f}")
    if meta.get("sqft"):
        print(f"  Size          : {meta['sqft']:,} sq ft")
    if meta.get("year_built"):
        print(f"  Year Built    : {meta['year_built']}")

    print()
    print("-" * 60)
    print("AI BREAKDOWN")
    print("-" * 60)
    try:
        explanation = get_explanation(address, arv, calc, meta)
        print(explanation)
    except Exception as e:
        print(f"(AI explanation unavailable: {e})")

    print()


if __name__ == "__main__":
    main()
