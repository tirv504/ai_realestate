import pandas as pd

# --- THE SKIP-TRACE PREPARER V1.0 ---
INPUT_FILE = "hot_deals_ready_for_zapier.csv"
OUTPUT_FILE = "ready_for_skip_trace.csv"

def prep():
    print("🧹 Grooming 1,303 leads for the skip tracer...")
    try:
        df = pd.read_csv(INPUT_FILE)

        # 1. Standardize Address: Add 'Houston, TX' to ensure accuracy
        df['site_addr_1'] = df['site_addr_1'] + ", Houston, TX"

        # 2. Keep only what the skip tracer needs (Privacy & Speed)
        # Most tracers just need: Address, City, State, Zip
        # Since we added Houston, TX above, we just send the full address column
        upload_df = df[['site_addr_1', 'tot_mkt_val', 'MAO']].copy()
        
        # 3. Export
        upload_df.to_csv(OUTPUT_FILE, index=False)
        print(f"✅ Success! Your 'ready_for_skip_trace.csv' is in your user folder.")

    except Exception as e:
        print(f"❌ Error: {e}")

prep()