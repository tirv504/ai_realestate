import pandas as pd

def generate_mvp():
    print("--- HCAD MVP SPRINT: TARGET 10 OUTPUTS ---")
    
    # Load a subset to keep it fast and simple
    # HCAD files are usually tab-delimited (\t)
    try:
        df = pd.read_csv('real_acct', sep='\t', nrows=5000, low_memory=False)
    except:
        # If it's a CSV or named differently, adjust here
        df = pd.read_csv('real_acct.csv', nrows=5000)

    # 1. THE FILTER (1980 / 1500)
    # Mapping HCAD headers (Adjust these if your file uses different names)
    # Typical: yr_blt, bld_ar, tot_mkt_val, site_addr_1
    filtered = df[(df['yr_blt'] < 1980) & (df['bld_ar'] > 1500)].head(10).copy()

    results = []

    for _, row in filtered.iterrows():
        # DATA EXTRACTION
        addr = f"{row['site_addr_1']} {row['site_addr_2']}".strip()
        val = row['tot_mkt_val']
        sqft = row['bld_ar']
        year = int(row['yr_blt'])

        # STEP 2: THE OFFER FORMULA
        offer = (val * 0.70) - (sqft * 30) - 10000

        # STEP 3: THE REASON
        reason = f"This offer is conservative because the home was built in {year} and likely needs system updates (roof/HVAC). The price includes a repair buffer based on the {sqft:,} sqft size."

        # STEP 4: THE OUTREACH MESSAGE
        if offer > 80000:
            msg = (f"Hi {row.get('owner_name', 'Owner')}, I’m a local investor looking at your property at {addr}. "
                   f"Based on recent data, I could potentially offer around ${offer:,.0f} as-is. "
                   f"Would you be open to a quick conversation?")
        else:
            msg = (f"Hi {row.get('owner_name', 'Owner')}, I’m looking at properties in your area. "
                   f"I wanted to ask: what is the current condition of the home at {addr}? "
                   f"Happy to connect if you’re considering selling.")

        results.append({
            'Address': addr,
            'Offer': f"${offer:,.2f}",
            'Reason': reason,
            'Outreach message': msg
        })

    # OUTPUT: THE CLEAN 4-COLUMN CSV
    output_df = pd.DataFrame(results)
    output_df.to_csv("houston_offers_v1.csv", index=False)
    print(f"SUCCESS: Created houston_offers_v1.csv with {len(output_df)} leads.")

if __name__ == "__main__":
    generate_mvp()