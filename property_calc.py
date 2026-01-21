# mao_tool.py (V0.4: ZERO-COST AVM with Construction Cost & Lead Score)

# --- 1. CONSTANTS (Your Proprietary Data/The Cost Matrix) ---
# ADJUST THESE COSTS BASED ON YOUR SPECIFIC HOUSTON-AREA EXPERIENCE!
COST_MATRIX = {
    "ROOF_REPLACEMENT": 12000.00,  
    "HVAC_REPLACEMENT": 8000.00,   
    "FULL_KITCHEN_RENO": 15000.00, 
    "PER_BATHROOM_RENO": 5000.00,  
    "PER_SQFT_COSMETIC": 10.00,    # For paint, flooring, trim
}

# --- 2. CORE LOGIC FUNCTIONS ---

def calculate_detailed_repairs(year_built: int, sqft: int, baths: float) -> float:
    """Calculates repairs by summing component costs based on property features."""
    total_cost = 0.0
    
    # 1. Age-based Triggers (Systems likely need replacement)
    # If built before 1980, assume major systems (roof/HVAC) are end-of-life
    if year_built < 1980:
        total_cost += COST_MATRIX["ROOF_REPLACEMENT"]
        total_cost += COST_MATRIX["HVAC_REPLACEMENT"]
    
    # 2. Renovation Costs (Triggered for typical flips)
    total_cost += COST_MATRIX["FULL_KITCHEN_RENO"]
    total_cost += COST_MATRIX["PER_BATHROOM_RENO"] * baths
    
    # 3. Square Footage Triggers
    total_cost += COST_MATRIX["PER_SQFT_COSMETIC"] * sqft
    
    # 4. Final Contingency 
    total_cost *= 1.15 
    
    return total_cost


def calculate_lead_score(ownership_years: int) -> dict:
    """Calculates a simple motivation score based on ownership length."""
    score = 0
    flags = []
    
    # Flag 1: Long Ownership (>10 years means they've paid down debt)
    if ownership_years >= 10:
        score += 1
        flags.append("Long Ownership (>10 Yrs)")
    
    # Flag 2: Extreme Longevity (>15 years means deep roots and likely max equity)
    if ownership_years >= 15:
        score += 1
        flags.append("High Equity (Likely Paid Off)")
        
    return {"score": score, "flags": flags}


def mao_calculator(arv: float, repairs: float, wholesale_fee: float = 10000.00, target_margin: float = 0.70) -> str:
    """
    Calculates the Maximum Allowable Offer (MAO).
    """
    try:
        target_purchase_price = (arv * target_margin) - repairs
        mao = target_purchase_price - wholesale_fee
        return f"Maximum Allowable Offer (MAO): ${mao:,.2f}"
    except Exception as e:
        return f"Error during calculation: {e}"


def get_free_property_data_manual(address: str) -> dict:
    """
    Simulates API call by asking the user to manually enter data 
    from a free source (County Assessor).
    """
    print(f"\n--- MANUAL DATA STEP for {address} ---")
    print("ACTION: Please look up this property on your local County Assessor website.")
    
    # Required Inputs (ALL NEED TO BE MANUALLY INPUTTED)
    arv_proxy = input("Enter County Assessed Value (e.g., 250000): $")
    year_built = input("Enter Year Built (e.g., 1955): ")
    sqft_input = input("Enter Square Footage (e.g., 1500): ")
    baths_input = input("Enter Total Number of Bathrooms (e.g., 2.5): ")
    ownership_input = input("Enter Years of Ownership (e.g., 12): ") 

    try:
        # Convert all inputs to usable numbers
        arv = float(arv_proxy)
        year = int(year_built)
        sqft = int(sqft_input)
        baths = float(baths_input) 
        owner_years = int(ownership_input)
    except ValueError:
        print("Invalid number input. Returning zero.")
        # Return a structure with defaults to prevent crashing
        return {"arv": 0.0, "repairs": 0.0, "lead_score": 0, "lead_flags": []}

    # CALCULATE REPAIRS & SCORE
    repairs = calculate_detailed_repairs(year, sqft, baths)
    score_data = calculate_lead_score(owner_years)
         
    return {
        "arv": arv, 
        "repairs": repairs, 
        "lead_score": score_data["score"],
        "lead_flags": score_data["flags"]
    }

# --- 3. MAIN EXECUTION FLOW ---
def qualify_lead_free(address: str):
    print("\n--- ZERO-COST AVM LEAD QUALIFIER V0.4 ---")
    property_data = get_free_property_data_manual(address)
    
    live_arv = property_data.get("arv", 0.0)
    estimated_repairs = property_data.get("repairs", 0.0)
    lead_score = property_data.get("lead_score", 0)
    lead_flags = property_data.get("lead_flags", [])

    if live_arv > 0:
        print(f"\n--- MAO CALCULATION ---")
        print(f"Using ARV Proxy: ${live_arv:,.2f}")
        print(f"Proprietary Repair Estimate: ${estimated_repairs:,.2f}")
        
        final_offer = mao_calculator(live_arv, estimated_repairs)
        
        print(f"\nFinal Offer for {address}:")
        print(final_offer)
        
        # FINAL DECISION: Based on the Lead Score
        print(f"\n--- LEAD MOTIVATION SCORE ---")
        print(f"Score: {lead_score}/2")
        print(f"Flags: {', '.join(lead_flags) if lead_flags else 'Low Motivation Indicators'}")

        if lead_score < 2:
             print("\nDECISION: ⚠️ **COLD LEAD.** Offer may not be accepted. Prioritize leads with a score of 2/2.")
        else:
             print("\nDECISION: ✅ **HOT LEAD!** Strong motivation indicators detected. Proceed with offer.")
        
    else:
        print("MAO calculation failed due to invalid data.")
        
# Example Usage (This starts the program):
target_address = "123 Main St, Houston, TX" 
qualify_lead_free(target_address)