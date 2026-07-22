import pandas as pd

INPUT_FILE = "real_acct.txt"
OUTPUT_FILE = "absentee_strike_list.csv"
CHUNK_SIZE = 250_000

MAX_YEAR = 1980
MIN_SQFT = 1500

def run_absentee_filter():
    print("Running Absentee Strike Logic...")

    collected = []

    # Using delimiter="\t" and adding handling for potential encoding or bad lines if necessary, 
    # but sticking to user provided code for now. User code used sep="\t".
    # Added encoding='ISO-8859-1' as a safety measure for HCAD data which often uses it, 
    # but the user didn't specify it. I'll stick to their code exactly first.
    
    for chunk in pd.read_csv(INPUT_FILE, sep="\t", chunksize=CHUNK_SIZE, low_memory=False, encoding='ISO-8859-1', on_bad_lines='warn'): 
        # Note: Added encoding='ISO-8859-1' because real_acct.txt usually requires it on Windows, 
        # but otherwise following user structure.
        
        # Base Sniper Mask
        mask = (
            (chunk["state_class"].str.strip() == "A1") &
            (pd.to_numeric(chunk["yr_impr"], errors="coerce") < MAX_YEAR) &
            (pd.to_numeric(chunk["bld_ar"], errors="coerce") > MIN_SQFT)
        )

        # Absentee Mask
        absentee_mask = (
            chunk["site_addr_1"].str.strip().str.upper() !=
            chunk["mail_addr_1"].str.strip().str.upper()
        )

        final_mask = mask & absentee_mask

        filtered = chunk.loc[final_mask]

        if not filtered.empty:
            collected.append(filtered)

    if collected:
        final_df = pd.concat(collected)
        final_df.to_csv(OUTPUT_FILE, index=False)
        print("Absentee file created.")
    else:
        print("No absentee properties found.")

if __name__ == "__main__":
    run_absentee_filter()
