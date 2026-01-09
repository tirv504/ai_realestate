import pandas as pd

INPUT_PATH = r"/mnt/data/KindSkiptracing - pre 1980 1500plus - Kind Original File - All Phone Types.csv"
OUTPUT_PATH = "outreach_ready.csv"

def pick_col(cols, candidates):
    cols_lower = {c.lower().strip(): c for c in cols}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    return None

def clean_phone(x):
    if pd.isna(x):
        return ""
    s = str(x)
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    return s

def choose_action(offer_proxy: float) -> str:
    if pd.isna(offer_proxy):
        return "ASK_CONDITION"
    if offer_proxy < 80000:
        return "ASK_CONDITION"
    return "SEND_OFFER"

def main():
    df = pd.read_csv(INPUT_PATH)

    # --- Column detection (robust) ---
    owner_col = pick_col(df.columns, [
        "owner name", "first name", "matched first name", "owner firstname", "owner first name"
    ])
    address_col = pick_col(df.columns, [
        "property address", "address", "site address"
    ])
    phone_col = pick_col(df.columns, [
        "mobile number", "owner mobile 1", "owner mobile", "phone", "owner phone"
    ])
    # If you already have an offer/mao column, use it directly
    offer_col = pick_col(df.columns, [
        "mao (your offer)", "mao", "offer", "offer proxy", "offer_proxy", "initial offer"
    ])
    # Otherwise we need some value proxy to base it on
    value_col = pick_col(df.columns, [
        "est value", "estimated value", "total assessed value", "assessed value", "market value"
    ])
    sqft_col = pick_col(df.columns, ["building sqft", "sqft", "living area", "building sq ft"])

    missing = [("owner", owner_col), ("address", address_col), ("phone", phone_col)]
    missing = [name for name, col in missing if col is None]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}. "
                           f"Your file has these columns:\n{list(df.columns)}")

    out = df.copy()

    # --- Build Offer_Proxy ---
    if offer_col is not None:
        out["Offer_Proxy"] = pd.to_numeric(out[offer_col], errors="coerce")
    else:
        # Basic first-pass fallback if no offer exists in file:
        # OfferProxy = 0.70*ValueProxy - RepairsHeuristic - 10k fee
        if value_col is None:
            raise RuntimeError("No MAO/Offer column found AND no value proxy column found. "
                               "Need at least one of those.")
        value_proxy = pd.to_numeric(out[value_col], errors="coerce").fillna(0)

        # Repairs heuristic (simple): 25$/sf if sqft exists, else 30% of value proxy
        if sqft_col is not None:
            sqft = pd.to_numeric(out[sqft_col], errors="coerce").fillna(0)
            repairs = sqft * 25.0
        else:
            repairs = value_proxy * 0.30

        out["Offer_Proxy"] = (value_proxy * 0.70) - repairs - 10000

    # --- Action & Message ---
    out["Action"] = out["Offer_Proxy"].apply(choose_action)

    out["Owner_Name"] = out[owner_col].fillna("").astype(str).str.strip()
    out["Property_Address"] = out[address_col].fillna("").astype(str).str.strip()
    out["Phone"] = out[phone_col].apply(clean_phone)

    def make_message(row):
        name = row["Owner_Name"] if row["Owner_Name"] else "there"
        addr = row["Property_Address"]
        offer = row["Offer_Proxy"]

        if row["Action"] == "ASK_CONDITION":
            return (f"Hi {name}, quick question about {addr} — "
                    f"is the home currently livable, or would it need a full rehab/teardown? "
                    f"That one detail changes the range a lot.")
        else:
            return (f"Hi {name}, I’m looking at {addr}. "
                    f"Based on current renovation costs, would you consider an offer around "
                    f"${offer:,.0f}?")

    out["Message_Draft"] = out.apply(make_message, axis=1)

    # --- Export a clean view ---
    export_cols = ["Owner_Name", "Property_Address", "Phone", "Offer_Proxy", "Action", "Message_Draft"]
    out[export_cols].to_csv(OUTPUT_PATH, index=False)

    print("\nSaved:", OUTPUT_PATH)
    print(out[export_cols].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
