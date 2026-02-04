import pandas as pd
import os

# --- 1. CONFIGURATION (First Principles) ---
INPUT_FILE = 'real_acct.txt'
OUTPUT_FILE = 'outreach_ready.csv'

def run_total_automation():
    print(f"--- 🚀 THE ALGORITHM: STARTING ALPHA STRIKE ---")
    
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: {INPUT_FILE} not found in this folder.")
        return

    # 2. ACCELERATED INGESTION
    # We only pull the 5 columns that actually matter to the mission.
    # Encoding 'latin1' handles legacy government data errors.
    cols = ['site_addr_1', 'tot_mkt_val', 'yr_impr', 'bld_ar', 'state_class']
    
    print("Reading Harris County Database...")
    try:
        df = pd.read_csv(INPUT_FILE, sep='\t', usecols=cols, encoding='latin1', low_memory=False)
    except Exception as e:
        print(f"❌ Critical Read Error: {e}")
        return

    # 3. UN-DUMB THE REQUIREMENTS (Strict Schema)
    # Convert strings to numbers immediately so the machine can math.
    df['yr_impr'] = pd.to_numeric(df['yr_impr'], errors='coerce')
    df['bld_ar'] = pd.to_numeric(df['bld_ar'], errors='coerce')
    df['tot_mkt_val'] = pd.to_numeric(df['tot_mkt_val'], errors='coerce')

    # 4. DELETE THE NOISE (Residential Only)
    # Only A (Single Family) and B (Multifamily). 
    # Deletes Commercial, Vacant, and Industrial.
    mask = (
        (df['state_class'].str.startswith(('A', 'B'), na=False)) & 
        (df['yr_impr'] < 1980) & 
        (df['yr_impr'] > 1900) & 
        (df['bld_ar'] > 1500) &
        (df['tot_mkt_val'] > 0)
    )
    
    strike_df = df[mask].copy()

    # 5. SIMPLIFY (HCAD Market Value = Offer)
    # We delete the "Price Guessing" process and use the Public Truth anchor.
    strike_df = strike_df.rename(columns={
        'site_addr_1': 'Property_Address',
        'tot_mkt_val': 'Offer_Price',
        'yr_impr': 'Year_Built',
        'bld_ar': 'Sq_Ft'
    })

    # 6. AUTOMATE OUTREACH (The Ping)
    # A low-friction message designed to elicit a response, not a rejection.
    def generate_ping(row):
        return f"Hi, I was looking at the house on {row['Property_Address']}. Would you be open to a cash offer this week?"

    strike_df['SMS_Message'] = strike_df.apply(generate_ping, axis=1)

    # 7. EXPORT (The Strike List)
    # We take the top 100 highest-probability residential leads.
    final_cols = ['Property_Address', 'Offer_Price', 'Sq_Ft', 'Year_Built', 'SMS_Message']
    strike_df[final_cols].head(100).to_csv(OUTPUT_FILE, index=False)
    
    print(f"✅ SUCCESS: {len(strike_df)} Residential Leads Identified.")
    print(f"🚀 Outreach file generated: '{OUTPUT_FILE}'")
    print("-" * 30)
    print(f"TOP STRIKE: {strike_df.iloc[0]['Property_Address']}")
    print(f"OFFER: ${strike_df.iloc[0]['Offer_Price']:,.0f}")
    print(f"MESSAGE: {strike_df.iloc[0]['SMS_Message']}")

if __name__ == "__main__":
    run_total_automation()