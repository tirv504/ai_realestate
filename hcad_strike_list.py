import os
import pandas as pd

# ----------------------------
# CONFIG
# ----------------------------
INPUT_FILE = "real_acct.txt"
OUTPUT_FILE = "outreach_ready.csv"

# How many rows to read per chunk (bigger = faster, smaller = less RAM)
CHUNK_SIZE = 250_000

# How many leads to export (keep it lean for outreach/testing)
EXPORT_LIMIT = 100

# “Sniper” guardrails (tweak if you want more/less chaos)
MIN_YEAR = 1900
MAX_YEAR = 1980
MIN_SQFT = 1200
MAX_SQFT = 3000
MIN_VALUE = 80_000
MAX_VALUE = 350_000

# Columns we actually need from HCAD
USE_COLS = ["site_addr_1", "site_addr_2", "tot_mkt_val", "yr_impr", "bld_ar", "state_class"]


def generate_sms(addr: str) -> str:
    return f"Hi, I was looking at the property at {addr}. Would you be open to a cash offer this week?"


def run_hcad_strike_list():
    print("\n--- HCAD STRIKE LIST: START ---")

    if not os.path.exists(INPUT_FILE):
        print(f"❌ ERROR: '{INPUT_FILE}' not found in this folder.")
        print("Put real_acct.txt next to this script, then run again.")
        return

    hits = 0
    kept_frames = []

    # Chunked read so your machine doesn’t get smoked by the 877MB file
    reader = pd.read_csv(
        INPUT_FILE,
        sep="\t",
        usecols=USE_COLS,
        encoding="latin1",
        low_memory=False,
        chunksize=CHUNK_SIZE,
    )

    for i, chunk in enumerate(reader, start=1):
        # Clean strings
        chunk["state_class"] = chunk["state_class"].astype(str).str.strip()
        chunk["site_addr_1"] = chunk["site_addr_1"].fillna("").astype(str).str.strip()
        chunk["site_addr_2"] = chunk["site_addr_2"].fillna("").astype(str).str.strip()

        # Numeric cleanup
        chunk["Effective_Year"] = pd.to_numeric(chunk["yr_impr"], errors="coerce")
        chunk["Sq_Ft"] = pd.to_numeric(chunk["bld_ar"], errors="coerce")
        chunk["HCAD_Market_Value"] = pd.to_numeric(chunk["tot_mkt_val"], errors="coerce")

        # Core filter (your sniper mask)
        mask = (
            (chunk["state_class"] == "A1") &
            (chunk["Effective_Year"] < MAX_YEAR) &
            (chunk["Effective_Year"] > MIN_YEAR) &
            (chunk["Sq_Ft"] > MIN_SQFT) &
            (chunk["Sq_Ft"] < MAX_SQFT) &
            (chunk["HCAD_Market_Value"] >= MIN_VALUE) &
            (chunk["HCAD_Market_Value"] <= MAX_VALUE)
        )

        filtered = chunk.loc[mask, ["site_addr_1", "site_addr_2", "HCAD_Market_Value", "Sq_Ft", "Effective_Year"]].copy()

        if not filtered.empty:
            # Combine address
            filtered["Property_Address"] = (filtered["site_addr_1"] + " " + filtered["site_addr_2"]).str.replace(r"\s+", " ", regex=True).str.strip()

            # Your “offer anchor” (NOT sent in the text)
            filtered["Offer"] = filtered["HCAD_Market_Value"]

            # Outreach message (soft ping)
            filtered["SMS_Message"] = filtered["Property_Address"].apply(generate_sms)

            # Keep only what matters
            filtered = filtered[["Property_Address", "Offer", "Sq_Ft", "Effective_Year", "SMS_Message"]]

            kept_frames.append(filtered)
            hits += len(filtered)

        print(f"Chunk {i}: kept {len(filtered)} | total kept so far: {hits}")

        # Stop early once we have enough leads to export (Lean + fast feedback loop)
        if hits >= EXPORT_LIMIT:
            break

    if not kept_frames:
        print("❌ No matches found with current filters.")
        print("Try raising EXPORT_LIMIT or loosening MIN/MAX ranges.")
        return

    strike_df = pd.concat(kept_frames, ignore_index=True)

    # Optional: prioritize “cheaper” properties first (often more motivated)
    strike_df = strike_df.sort_values("Offer", ascending=True)

    # Export only the top N
    final_df = strike_df.head(EXPORT_LIMIT).copy()
    final_df.to_csv(OUTPUT_FILE, index=False)

    print("\n✅ SUCCESS")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Exported leads: {len(final_df)}")
    print("\nTOP 3 PREVIEW:")
    print(final_df.head(3).to_string(index=False))


if __name__ == "__main__":
    run_hcad_strike_list()
