import pandas as pd
import os

# --- IMPORTANT: REPLACE 'YOUR_FILE_NAME' WITH THE ACTUAL PATH/NAME ---
# The path should be where the 'real_acct' file is located on your Windows system.
FILE_NAME = r"C:\ai_real_estate_tools\real_acct_data.csv\real_acct" # Assuming the file is in the same folder as this script

def inspect_large_file(file_name):
    print(f"Attempting to read the first 5 rows of: {file_name}")
    
    # Try reading as a standard comma-separated file (CSV)
    try:
        # We use 'nrows=5' to read only the first 5 lines, preventing memory overload.
        df = pd.read_csv(file_name, nrows=5)
        
        print("\n--- Success! First 5 Rows (Data Frame Head) ---")
        print(df)
        
        print("\n--- Data Types (to confirm how columns are read) ---")
        print(df.dtypes)

    except FileNotFoundError:
        print(f"\nERROR: File not found at {os.path.abspath(file_name)}")
        print("Please ensure the file is in the same directory or update the FILE_NAME variable.")
    except Exception as e:
        # This will catch errors if the file is NOT a standard CSV (e.g., if it's Tab-separated)
        print(f"\nERROR reading as standard CSV. The file might be corrupted or use a different delimiter (e.g., Tab). Error: {e}")

# Run the inspection
inspect_large_file(FILE_NAME)