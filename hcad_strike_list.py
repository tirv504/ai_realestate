import pandas as pd
import os

# --- CONFIG ---
INPUT_FILE = "real_acct.txt"
OUTPUT_FILE = "skiptrace_ready.csv"
CHUNK_SIZE = 250_000
EXPORT_LIMIT = 100

# Sniper Guardrails
MIN_YEAR, MAX_YEAR = 1900, 1980
MIN_SQFT, MAX_SQFT = 1200, 3000
MIN_VALUE, MAX_VALUE = 80_000, 350_000

# ADDED: Identity and Mailing Columns for Kind Skiptracing
USE_COLS = [
    "site_addr_1", "site_addr_2", "tot_mkt_val", "yr_impr", "bld_ar", "state_class",
    "mailto", "mail_addr_1", "mail_city", "mail_state", "mail_zip"
]

def run_hcad_strike_list():
    print("\n--- 🚀 ANTIGRAVITY MISSION: IDENTITY PULL ---")
    
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
        # 1. CORE FILTER (A1 Sniper Mask)
        # Note: We need to handle potential string/numeric conversion issues on the fly or beforehand
        # The user snippet implies doing it in the mask expression or before.
        # Let's clean the state_class first as usually done
        chunk["state_class"] = chunk["state_class"].astype(str).str.strip()
        
        mask = (
            (chunk["state_class"] == "A1") &
            (pd.to_numeric(chunk["yr_impr"], errors='coerce') < MAX_YEAR) &
            (pd.to_numeric(chunk["yr_impr"], errors='coerce') > MIN_YEAR) &
            (pd.to_numeric(chunk["bld_ar"], errors='coerce') < MAX_SQFT) &
            (pd.to_numeric(chunk["bld_ar"], errors='coerce') > MIN_SQFT) &
            (pd.to_numeric(chunk["tot_mkt_val"], errors='coerce') <= MAX_VALUE) &
            (pd.to_numeric(chunk["tot_mkt_val"], errors='coerce') >= MIN_VALUE)
        )
        
        filtered = chunk.loc[mask].copy()

        if not filtered.empty:
            # 2. IDENTITY CLEANUP: Split "LAST FIRST" format from HCAD
            # Kind Skiptracing performs better with separate First/Last name columns
            # Ensure mailto is string (it's the owner name)
            filtered["mailto"] = filtered["mailto"].fillna("").astype(str)
            name_split = filtered["mailto"].str.split(" ", n=1, expand=True)
            filtered["Last_Name"] = name_split[0].str.strip()
            
            if name_split.shape[1] > 1:
                filtered["First_Name"] = name_split[1].str.strip().fillna("Owner")
            else:
                filtered["First_Name"] = "Owner"


            # 3. ADDRESS CONSOLIDATION
            filtered["site_addr_1"] = filtered["site_addr_1"].fillna("").astype(str).str.strip()
            filtered["site_addr_2"] = filtered["site_addr_2"].fillna("").astype(str).str.strip()
            filtered["Property_Address"] = (filtered["site_addr_1"] + " " + filtered["site_addr_2"]).str.strip().str.replace(r"\s+", " ", regex=True)
            
            # 4. PREPARE FOR KIND SKIPTRACING (Required Headers)
            # We use Mailing Address because that's where the tax bill goes (the owner's actual location)
            # Rename mail_addr_1 to Mailing_Address, tot_mkt_val to Offer
            
            # Ensure mailing columns exist (they are in USE_COLS)
            
            export_df = filtered[[
                "First_Name", "Last_Name", "Property_Address", 
                "mail_addr_1", "mail_city", "mail_state", "mail_zip", 
                "tot_mkt_val"
            ]].rename(columns={"mail_addr_1": "Mailing_Address", "tot_mkt_val": "Offer"})
            
            kept_frames.append(export_df)
            hits += len(filtered)
        
        print(f"Chunk {i}: kept {len(filtered)} | total kept so far: {hits}")

        if hits >= EXPORT_LIMIT:
            break
            
    if not kept_frames:
        print("❌ No matches found with current filters.")
        print("Try raising EXPORT_LIMIT or loosening MIN/MAX ranges.")
        return

    strike_df = pd.concat(kept_frames, ignore_index=True)

    # Export only the top N
    final_df = strike_df.head(EXPORT_LIMIT).copy()
    final_df.to_csv(OUTPUT_FILE, index=False)

    print("\n✅ SUCCESS")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Exported rows: {len(final_df)}")
    print("\nTOP 3 PREVIEW:")
    print(final_df.head(3).to_string(index=False))

if __name__ == "__main__":
    run_hcad_strike_list()
