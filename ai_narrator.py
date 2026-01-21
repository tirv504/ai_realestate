import os
from openai import OpenAI

# 1. Initialize the Client
# Ensure your OPENAI_API_KEY is set in your environment variables
client = OpenAI()

def calculate_expert_mao(arv, repairs, risk_tier):
    """
    The 'Architect' Logic:
    Tier 1: Hot Market (80% Rule)
    Tier 2: Stable Market (70% Rule)
    Tier 3: Risky/Warzone (60% Rule)
    """
    multipliers = {1: 0.80, 2: 0.70, 3: 0.60}
    target_margin = multipliers.get(risk_tier, 0.70)
    
    # The 'Appraiser's Buffer': 15% contingency for hidden repair costs
    adjusted_repairs = repairs * 1.15
    
    # We set a standard wholesale fee of $10,000 for the prototype
    wholesale_fee = 10000
    
    mao = (arv * target_margin) - adjusted_repairs - wholesale_fee
    return mao

def ai_offer_analyst(arv, repairs, year_built, sqft, ownership_years, mao):
    prompt = f"""
You are a Senior Residential Appraiser and Investment Analyst. 
Speak with clinical objectivity and professional authority.

This is a FIRST-PASS offer justification.

Inputs:
- After Repair Value (ARV): ${arv:,.0f}
- Calculated Max Offer: ${mao:,.2f}
- Estimated Repairs: ${repairs:,.0f} (plus 15% contingency)
- Year Built: {year_built}
- Square Footage: {sqft}
- Ownership Years: {ownership_years}

Instructions:
1. Explain why this offer is conservative based on the age of the property ({year_built}) and current market risk.
2. Highlight how the "15% Expert Contingency" on repairs protects the deal.
3. Identify 1 specific risk common to houses from {year_built} (e.g., cast iron pipes, electrical, foundation) that justifies this price point.
4. End with: "This analysis is generated via The Royce Protocol. Professional inspection required."
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini", # Using the 2026 standard for fast reasoning
        messages=[{"role": "system", "content": "You are a professional real estate specialist."},
                  {"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content

def main():
    print("--- THE ROYCE PROTOCOL v1.0 ---")
    
    # Inputs
    arv = float(input("Enter ARV: "))
    repairs = float(input("Enter Estimated Repairs: "))
    year_built = int(input("Enter Year Built: "))
    sqft = int(input("Enter Square Footage: "))
    ownership_years = int(input("Years of Ownership: "))
    
    print("\nSelect Risk Tier:")
    print("1: Hot/Premium | 2: Standard | 3: High Risk")
    risk_tier = int(input("Tier: "))

    # Calculation
    mao = calculate_expert_mao(arv, repairs, risk_tier)

    # AI Reasoning
    print("\nGenerating Expert Justification...\n")
    justification = ai_offer_analyst(arv, repairs, year_built, sqft, ownership_years, mao)

    # Output
    print("="*40)
    print(f"FINAL MAO: ${mao:,.2f}")
    print("="*40)
    print(justification)

if __name__ == "__main__":
    main()