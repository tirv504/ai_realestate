import pandas as pd

def run_sprint():
    print("--- 🚀 SPRINT: PULLING PRE-1980 / 1500 SQFT LEADS ---")
    
    # 1. READ RAW HCAD DATA
    # Reading 50k rows to ensure we find 10 that fit the strict criteria
    df = pd.read_csv('real_acct.txt', sep='\t', nrows=50000, low_memory=False)

    # 2. THE NUMERIC FIX (Don't skip this - it makes the math work)
    df['yr_impr'] = pd.to_numeric(df['yr_impr'], errors='coerce')
    df['bld_ar'] = pd.to_numeric(df['bld_ar'], errors='coerce')

    # 3. APPLY THE LOGIC
    # A1 = Single Family | Built < 1980 | Size > 1500
    mask = (
        (df['state_class'].str.startswith('A', na=False)) & 
        (df['yr_impr'] < 1980) & 
        (df['yr_impr'] > 1900) & # Ignore '0' or error years
        (df['bld_ar'] > 1500)
    )
    
    results_df = df[mask].head(10).copy()

    # 4. OUTPUT THE GOLD
    if not results_df.empty:
        results_df.to_csv("houston_10_drafts.csv", index=False)
        print(f"✅ SUCCESS: Found {len(results_df)} leads matching 1980/1500 logic.")
        print("File created: houston_10_drafts.csv")
    else:
        print("❌ NO MATCHES: Try increasing 'nrows' in the script to search deeper.")

if __name__ == "__main__":
    run_sprint()