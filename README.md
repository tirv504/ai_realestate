# AI Real Estate Tools (Houston Operations)

A comprehensive suite of Python tools designed for real estate investment operations, specifically tailored for the Houston market (HCAD data). This project automates lead identification, offer calculation (MAO), data scrubbing, and outreach message generation.

## 🚀 Quick Start

1.  **Install Dependencies**:
    ```bash
    pip install pandas openpyxl openai
    ```
2.  **Run the Main Pipeline**:
    The easiest way to process your raw list (`1st.xlsx`) into a campaign-ready file is:
    ```bash
    python 1980_1500_pipeline.py
    ```
    This generates `outreach_ready.csv` containing cleaned data and drafted outreach messages.

## 📂 Project Structure

### Core Pipelines
*   **`1980_1500_pipeline.py`**: The master automation script.
    *   **Step 1**: Runs `scrub_new_list.py` to filter raw data (Pre-1980, >1500 sqft).
    *   **Step 2**: Runs `make_outreach_ready.py` to format phone numbers, calculate offers, and draft messages.
    *   **Output**: `outreach_ready.csv` (Ready for SMS/RVM).

### Individual Tools

#### 1. Lead Scrubbing & Filtering
*   **`scrub_new_list.py`**:
    *   **Input**: `1st.xlsx` (Raw Excel list).
    *   **Logic**: Filters for properties built before 1980 and larger than 1,500 sqft ("The Gold Digger" logic). Calculates initial MAO.
    *   **Output**: `ready_for_kind_emails.csv`.
*   **`hcad_mvp.py`**:
    *   **Input**: `real_acct` (HCAD data dump).
    *   **Purpose**: Lightweight MVP for processing raw HCAD text files. Creates `houston_offers_v1.csv` with a simple 4-column output.

#### 2. Outreach Preparation
*   **`make_outreach_ready.py`**:
    *   **Input**: CSV or Excel file (default: `ready_for_kind_emails.csv`).
    *   **Features**: Smart column detection (fuzzy matching for Owner, Phone, Address), phone number formatting `(XXX) XXX-XXXX`, and dynamic message generation ("Ask Condition" vs "Send Offer").
    *   **Output**: `outreach_ready.csv`.
*   **`skip_prep.py`**:
    *   **Input**: `hot_deals_ready_for_zapier.csv`.
    *   **Purpose**: Prepares a simplified file for skip-tracing services, ensuring addresses include "Houston, TX".
    *   **Output**: `ready_for_skip_trace.csv`.

#### 3. Calculators & Analysis
*   **`property_calc.py`**: **Zero-Cost AVM & Lead Score**.
    *   **Usage**: interactive CLI tool.
    *   **Function**: Manually enter property details (Year Built, Sqft, etc.) to get a detailed repair estimate based on a cost matrix (Roof, HVAC, Kitchen) and a "Lead Motivation Score" based on ownership length.
*   **`ai_narrator.py`** (formerly `appraiser_engine.py`): **The Royce Protocol**.
    *   **Usage**: interactive CLI tool.
    *   **Requirement**: `OPENAI_API_KEY` environment variable.
    *   **Function**: Uses OpenAI's GPT models to generate an "Expert Justification" for your offer, acting as a Senior Appraiser.

### Utilities
*   **`inspect_headers.py`**: simple utility to print the column headers of your data files (`ready_for_kind_emails.csv`, `1st.xlsx`) to debug column mapping issues.

## ⚙️ Configuration & Notes

*   **Cost Matrix**: Repair costs are defined in `property_calc.py` within the `COST_MATRIX` dictionary. Adjust these values to match current contractor rates in Houston.
*   **Data Files**: Ensure your input files (like `1st.xlsx` or `real_acct`) are in the project root directory before running the scripts.
*   **OpenAI**: For `ai_narrator.py`, ensure you have an API key:
    *   Windows (PowerShell): `$env:OPENAI_API_KEY="sk-..."`
