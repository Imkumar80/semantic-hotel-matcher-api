import subprocess
import sys
import time

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
        "02_candidates.py",
        "03_score_hotels.py",
        "04_resolve_hotels.py",
        "05_merge_hotels.py",
        "06_parse_rooms.py",
        "07_match_rooms.py",
        "08_build_db.py"
    ]
    
    total_start = time.time()
    for stage in stages:
        run_stage(stage)
        
    total_end = time.time()
    print(f"\nPipeline completed successfully in {total_end - total_start:.2f} seconds.")
    print("Metrics are available in the stage logs above. SQLite DB is ready at data/canonical/hotels.db")

if __name__ == "__main__":
    main()
