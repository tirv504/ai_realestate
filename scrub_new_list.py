import pandas as pd

# --- THE EXCEL-DIRECT INNOVATION SCRUBBER ---
INPUT_FILE = "1st.xlsx" 
OUTPUT_FILE = "ready_for_kind_emails.csv"

def attack():
    print(f"Attacking {INPUT_FILE} directly...")
    try:
        # 1. Read the Excel file directly (No CSV conversion needed)
        df = pd.read_excel(INPUT_FILE)
        
        # 2. Standardize numbers for your Appraisal logic
        df['Effective Year Built'] = pd.to_numeric(df['Effective Year Built'], errors='coerce')
        df['Building Sqft'] = pd.to_numeric(df['Building Sqft'], errors='coerce')
        df['Est Value'] = pd.to_numeric(df['Est Value'], errors='coerce')

        # 3. Apply the "Gold Digger" Logic: Pre-1980 + Over 1500 Sqft
        gold = df[(df['Effective Year Built'] < 1980) & (df['Building Sqft'] > 1500)].copy()

        # 4. Underwrite the MAO: (Value * 0.7) - (Sqft * 30) - 10k Fee
        # MAO = (ARV * 0.70) - Repairs - Fee
        gold['MAO'] = (gold['Est Value'] * 0.70) - (gold['Building Sqft'] * 30) - 10000

        # 5. Export for your 6,935 Kind Credits
        cols = ['First Name', 'Last Name', 'Address', 'City', 'State', 'Zip', 'MAO']
        gold[cols].to_csv(OUTPUT_FILE, index=False)
        print(f"Success! {len(gold)} high-probability deals ready in {OUTPUT_FILE}")

    except Exception as e:
        print(f"Error: {e}")
        print(f"TIP: Ensure '{INPUT_FILE}' is in C:\\Users\\lirving3661")

if __name__ == "__main__":
    attack()
