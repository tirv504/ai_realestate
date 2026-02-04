import pandas as pd
from google import genai

# --- 1. SETUP ---
client = genai.Client(api_key="YOUR_API_KEY_HERE")

def run_tiered_arv():
    print("\n--- 🔬 PROJECT ENOUGH THINKING: TIERED ARV SPRINT ---")
    
    try:
        df = pd.read_csv('houston_10_drafts.csv')
    except:
        print("❌ Error: 'houston_10_drafts.csv' not found.")
        return
    
    results = []
    for index, row in df.iterrows():
        address = row['site_addr_1']
        sqft = int(row['bld_ar'])
        current_val = row['tot_mkt_val'] # Current HCAD Market Value
        
        # The Tiered Prompt: Forces the AI to find the floor and the ceiling
        prompt = f"""
        Act as a Houston Real Estate Analyst. Analyze ARV tiers for: {address}.
        Specs: {sqft} sqft. Current HCAD Value: ${current_val}.

        TASK: Find 3 comps for EACH of the following tiers within 0.5 miles:
        
        TIER 1 (Rental/Partial): Clean, functional, basic updates (paint/flooring). 
        TIER 2 (Retail/Extensive): Fully renovated kitchen/baths, modern finishes. 
        TIER 3 (Premium/Total): To-the-studs remodel or high-end luxury overhaul.

        OUTPUT FORMAT:
        - Tier 1 Avg Price: 
        - Tier 2 Avg Price: 
        - Tier 3 Avg Price: 
        - Recommended Exit: (Based on the largest spread vs. Current HCAD Value)
        """
        
        print(f"[{index+1}/10] Analyzing Tiers for {address}...")
        
        try:
            response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
            results.append({
                "Address": address,
                "Current_HCAD": current_val,
                "Tier_Analysis": response.text.strip()
            })
        except Exception as e:
            print(f"⚠️ Failed: {e}")

    pd.DataFrame(results).to_csv("tiered_market_analysis.csv", index=False)
    print("\n🚀 DONE. Open 'tiered_market_analysis.csv'.")

if __name__ == "__main__":
    run_tiered_arv()