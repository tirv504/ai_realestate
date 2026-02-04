import pandas as pd

def generate_hcad_offers():
    # 1. Load the verified data
    try:
        df = pd.read_csv('houston_10_drafts.csv')
    except:
        print("❌ Error: 'houston_10_drafts.csv' not found.")
        return

    # 2. Step 3: Simplify (The Offer is the HCAD Value)
    # No multipliers, no FRED API, no complex math.
    print("Executing First Principles Strike: Offer = HCAD Market Value...")
    
    df['Offer_Price'] = df['HCAD_Value']

    # 3. Step 2: Delete everything but the strike data
    output_cols = ['Property_Address', 'HCAD_Value', 'Offer_Price']
    final_list = df[output_cols].copy()

    # 4. Step 5: Automate Output
    final_list.to_csv('hcad_strike_list.csv', index=False)
    
    print(f"✅ DONE: {len(final_list)} Offers ready in 'hcad_strike_list.csv'.")
    print(f"Sample Strike: {final_list.iloc[0]['Property_Address']} | Offer: ${final_list.iloc[0]['Offer_Price']:,.0f}")

if __name__ == "__main__":
    generate_hcad_offers()