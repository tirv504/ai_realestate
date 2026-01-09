import pandas as pd
import os

files = ["ready_for_kind_emails.csv", "1st.xlsx"]
for f in files:
    if os.path.exists(f):
        print(f"\n--- Headers for {f} ---")
        try:
            if f.endswith('.csv'):
                df = pd.read_csv(f, nrows=1)
            else:
                df = pd.read_excel(f, nrows=1)
            print(list(df.columns))
        except Exception as e:
            print(f"Error reading {f}: {e}")
    else:
        print(f"\n--- {f} not found ---")
