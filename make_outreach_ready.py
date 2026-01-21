import pandas as pd
import argparse
import logging
import sys
import os
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def pick_col(cols: List[str], candidates: List[str]) -> Optional[str]:
    """Finds the first matching column name from candidates in the actual columns (case-insensitive)."""
    cols_lower = {c.lower().strip(): c for c in cols}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None

def clean_phone(x: Any) -> str:
    """Standardizes phone numbers to (XXX) XXX-XXXX format."""
    if pd.isna(x):
        return ""
    s = str(x).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    
    # Handle cases with leading 1 (e.g. 15551234567)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
        
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    return s

def choose_action(offer_proxy: float) -> str:
    """Determines the action based on the offer amount."""
    if pd.isna(offer_proxy) or offer_proxy < 80000:
        return "ASK_CONDITION"
    return "SEND_OFFER"

def make_message(row: pd.Series) -> str:
    """Generates the outreach message."""
    name = str(row.get("Owner_Name", "")).strip()
    if not name or name.lower() == "nan":
        name = "there"
        
    addr = str(row.get("Property_Address", "")).strip()
    offer = row.get("Offer_Proxy", 0)

    if row.get("Action") == "ASK_CONDITION":
        return (f"Hi {name}, quick question about {addr} — "
                f"is the home currently livable, or would it need a full rehab/teardown? "
                f"That one detail changes the range a lot.")
    else:
        return (f"Hi {name}, I’m looking at {addr}. "
                f"Based on current renovation costs, would you consider an offer around "
                f"${offer:,.0f}?")

def process_file(input_path: str, output_path: str):
    logger.info(f"Reading input file: {input_path}")
    
    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    try:
        if input_path.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(input_path)
        else:
            df = pd.read_csv(input_path)
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        sys.exit(1)

    logger.info(f"Columns found: {list(df.columns)}")
    with open("headers_debug.txt", "w") as f:
        f.write(str(list(df.columns)))


    # --- Column detection ---
    owner_col = pick_col(df.columns, [
        "owner name", "first name", "matched first name", "owner firstname", "owner first name", 
        "owner_name", "firstname", "first_name", "name"
    ])
    
    # If owner is missing but we have First and Last, we can try to use First Name as a fallback
    if not owner_col:
        first = pick_col(df.columns, ["first name", "firstname", "first_name"])
        last = pick_col(df.columns, ["last name", "lastname", "last_name"])
        if first:
            logger.info(f"Using '{first}' as Owner Name (Last Name: {last})")
            owner_col = first
            
    address_col = pick_col(df.columns, [
        "property address", "address", "site address", "site_address", "prop_addr", "addr", "site_addr_1"
    ])
    
    # Phone candidates
    phone_candidates = [
        "mobile number", "owner mobile 1", "owner mobile", "phone", "owner phone", 
        "wireless number", "cell phone", "phone_number", "cell", "mobile",
        "pager", "landline"
    ]
    pass_phone_col = pick_col(df.columns, phone_candidates)
    
    # Fallback to any column containing "phone" or "mobile" if strict match fails
    if not pass_phone_col:
        potential_phones = [c for c in df.columns if "phone" in c.lower() or "mobile" in c.lower()]
        if potential_phones:
            pass_phone_col = potential_phones[0]
            logger.info(f"Fuzzy matched phone column: {pass_phone_col}")
            
    # If still no phone, look for "Relative" phones or "PAGER"/"LANDLINE" as a last resort
    if not pass_phone_col:
         potential_relatives = [c for c in df.columns if ("relative" in c.lower() or "pager" in c.lower() or "landline" in c.lower()) and ("phone" in c.lower() or "mobile" in c.lower() or "landline" in c.lower() or "pager" in c.lower())]
         if potential_relatives:
             pass_phone_col = potential_relatives[0]
             logger.info(f"Using alternate phone column: {pass_phone_col}")

    offer_col = pick_col(df.columns, [
        "mao (your offer)", "mao", "offer", "offer proxy", "offer_proxy", "initial offer", "target offer"
    ])
    value_col = pick_col(df.columns, [
        "est value", "estimated value", "total assessed value", "assessed value", "market value",
        "tot_mkt_val", "market_value", "value"
    ])
    sqft_col = pick_col(df.columns, [
        "building sqft", "sqft", "living area", "building sq ft", "bld_ar", "square_feet"
    ])

    missing = []
    if not owner_col: missing.append("Owner Name")
    if not address_col: missing.append("Address")
    
    # We allow Phone to be missing now
    if not pass_phone_col:
        logger.warning("No phone column found. Outreach list will have empty phone numbers.")

    if missing:
        logger.error(f"Missing required columns: {', '.join(missing)}")
        logger.error(f"Available columns: {list(df.columns)}")
        sys.exit(1)

    logger.info(f"Mapped Columns: Owner='{owner_col}', Address='{address_col}', Phone='{pass_phone_col}'")

    out = df.copy()

    # --- Build Offer_Proxy ---
    if offer_col:
        logger.info(f"Using existing Offer column: {offer_col}")
        out["Offer_Proxy"] = pd.to_numeric(out[offer_col], errors="coerce")
    else:
        if not value_col:
            logger.error("No Offer/MAO column AND no Value Proxy column found. Cannot calculate offer.")
            sys.exit(1)
            
        logger.info(f"Calculating Offer from Value column: {value_col}")
        value_proxy = pd.to_numeric(out[value_col], errors="coerce").fillna(0)

        if sqft_col:
            sqft = pd.to_numeric(out[sqft_col], errors="coerce").fillna(0)
            repairs = sqft * 25.0
        else:
            repairs = value_proxy * 0.30

        out["Offer_Proxy"] = (value_proxy * 0.70) - repairs - 10000

    # --- Action & Message ---
    out["Action"] = out["Offer_Proxy"].apply(choose_action)
    out["Owner_Name"] = out[owner_col].fillna("").astype(str).str.strip()
    out["Property_Address"] = out[address_col].fillna("").astype(str).str.strip()
    
    if pass_phone_col:
        out["Phone"] = out[pass_phone_col].apply(clean_phone)
    else:
        out["Phone"] = ""
    
    out["Message_Draft"] = out.apply(make_message, axis=1)

    # --- Export ---
    export_cols = ["Owner_Name", "Property_Address", "Phone", "Offer_Proxy", "Action", "Message_Draft"]
    
    try:
        out[export_cols].to_csv(output_path, index=False)
        logger.info(f"Successfully saved {len(out)} rows to: {output_path}")
        
        # Preview
        print("\n--- Preview (Top 5) ---")
        print(out[export_cols].head(5).to_string(index=False))
        print("-----------------------\n")
        
    except Exception as e:
        logger.error(f"Failed to write output file: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Prepare real estate leads for outreach (SMS/RVM).")
    parser.add_argument("--input", "-i", required=False, default="ready_for_kind_emails.csv", help="Path to the input CSV/Excel file.")
    parser.add_argument("--output", "-o", required=False, default="outreach_ready.csv", help="Path to the output CSV file.")
    
    args = parser.parse_args()
    
    print(f"--- Real Estate Outreach Prep Tool ---")
    process_file(args.input, args.output)

if __name__ == "__main__":
    main()
