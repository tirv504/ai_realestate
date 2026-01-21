import os
import sys
import scrub_new_list
import make_outreach_ready

def run_the_system():
    print("STEP 1: SCRUBBING DATA...")
    # This takes 1st.xlsx -> ready_for_kind_emails.csv
    scrub_new_list.attack()

    if os.path.exists("ready_for_kind_emails.csv"):
        print("STEP 2: FORMATTING OUTREACH...")
        
        # We call the process_file function directly from the imported module
        # explicitly defining input and output paths
        make_outreach_ready.process_file(
            input_path="ready_for_kind_emails.csv",
            output_path="outreach_ready.csv"
        )
        
        print("\nSUCCESS: 'outreach_ready.csv' is ready for your 6,935 Kind Credits.")
    else:
        print("ERROR: Could not find 'ready_for_kind_emails.csv'. Did the scrub fail?")

if __name__ == "__main__":
    run_the_system()
