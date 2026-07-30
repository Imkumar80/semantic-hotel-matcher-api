import subprocess
import sys
import time
import os

def run_stage(stage_script):
    print(f"\n{'='*50}\nRunning {stage_script}...\n{'='*50}")
    start = time.time()
    result = subprocess.run([sys.executable, f"pipeline/{stage_script}"])
    end = time.time()
    if result.returncode != 0:
        print(f"Error running {stage_script}. Exiting.")
        sys.exit(1)
    print(f"[{stage_script}] completed in {end - start:.2f} seconds.")

def main():
    stages = [
        "01_preprocess.py",
        "02_splink_match.py",
        "03_resolve_hotels.py",
        "04_merge_hotels.py",
        "05_parse_rooms.py",
        "06_match_rooms.py",
        "07_build_db.py"
    ]
    
    total_start = time.time()
    for stage in stages:
        if os.path.exists(f"pipeline/{stage}"):
            run_stage(stage)
        else:
            print(f"Warning: {stage} not found, skipping.")
        
    total_end = time.time()
    print(f"\nPipeline completed successfully in {total_end - total_start:.2f} seconds.")
    print("Metrics are available in the stage logs above. SQLite DB is ready at data/canonical/hotels.db")

if __name__ == "__main__":
    main()
