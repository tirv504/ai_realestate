import pandas as pd

# --- THE COLD DIGGER V1.3 (Force Numbers Fix) ---
FILE_PATH = r"C:\ai_real_estate_tools\real_acct_data.csv\real_acct.txt"
OUTPUT_FILE = "hot_deals_ready_for_zapier.csv"

def run_production_line():
    print("🚀 Running Production Line... Scrubbing Harris County Data.")
    
    try:
        # Load the data with the Tab separator
        df = pd.read_csv(FILE_PATH, sep='\t', encoding='ISO-8859-1', on_bad_lines='skip', nrows=5000, low_memory=False)

        # --- THE FIX: FORCE COLUMNS TO NUMBERS ---
        # This converts text "1980" to number 1980. If it fails, it turns it into NaN (Empty).
        df['yr_impr'] = pd.to_numeric(df['yr_impr'], errors='coerce')
        df['bld_ar'] = pd.to_numeric(df['bld_ar'], errors='coerce')
        df['tot_mkt_val'] = pd.to_numeric(df['tot_mkt_val'], errors='coerce')

        # Drop rows where critical data is missing (NaN)
        df = df.dropna(subset=['yr_impr', 'bld_ar', 'tot_mkt_val'])

        # --- STEP 1: HARVEST ---
        # Filter: Built before 1980
        harvested = df[df['yr_impr'] < 1980].copy()

        # Filter: Bigger than 1500 sqft
        harvested = harvested[harvested['bld_ar'] > 1500]

        # --- STEP 2: UNDERWRITE ---
        # Math: (Market Value * 0.70) - ($30/sqft Repairs) - $10k Fee
        harvested['est_repairs'] = harvested['bld_ar'] * 30.00
        harvested['MAO'] = (harvested['tot_mkt_val'] * 0.70) - harvested['est_repairs'] - 10000

        # --- STEP 3: EXPORT ---
        gold_cols = ['acct', 'site_addr_1', 'yr_impr', 'bld_ar', 'tot_mkt_val', 'MAO']
        harvested[gold_cols].to_csv(OUTPUT_FILE, index=False)

        print(f"✅ BOOM! Found {len(harvested)} deals that fit your criteria.")
        print(f"📂 Saved to: {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_production_line()