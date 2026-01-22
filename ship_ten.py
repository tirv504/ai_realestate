import pandas as pd

def ship_ten():
    print("--- 🚀 SPRINT: GENERATING 10 HOUSTON DRAFTS ---")
    
    # 1. READ RAW DATA (Using the .txt extension we verified)
    try:
        df = pd.read_csv('real_acct.txt', sep='\t', nrows=10000, low_memory=False)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return

    # 2. FILTER FOR RESIDENTIAL
    # 'A1' is Single Family in Houston. We'll grab any 'A' class.
    res_mask = (df['state_class'].str.startswith('A', na=False)) & (df['bld_ar'] > 1500)
    top_ten = df[res_mask].head(10).copy()

    results = []

    for _, row in top_ten.iterrows():
        # DATA MAPPING
        addr = f"{row['site_addr_1']}, Houston, TX {row['site_addr_3']}"
        val = float(row['tot_mkt_val'])
        sqft = float(row['bld_ar'])
        year = int(row['yr_impr']) if pd.notnull(row['yr_impr']) else "Older"

        # THE OFFER FORMULA (0.70 Rule)
        offer = (val * 0.70) - (sqft * 30) - 10000

        results.append({
            'Address': addr,
            'Offer': f"${offer:,.0f}",
            'Reason': f"Built/Improved: {year} | Size: {sqft:,.0f} sqft. Offer accounts for system updates.",
            'Outreach': f"Hi, I'm a local investor. I saw your property at {addr}. I could potentially offer around ${offer:,.0f} as-is. Open to a chat?"
        })

    # 3. SAVE THE OUTPUT
    output_file = "houston_10_drafts.csv"
    pd.DataFrame(results).to_csv(output_file, index=False)
    
    print(f"\n✅ SUCCESS! Target Reached.")
    print(f"📄 File created: {output_file}")
    print("Next Step: Open this file and verify the first 10 leads.")

if __name__ == "__main__":
    ship_ten()