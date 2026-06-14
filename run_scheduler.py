import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent))
import directory

# --- Argparse Setting ---
parser = argparse.ArgumentParser(description="SOLO Scheduler: Queue existing YAML plans in Windows Task Scheduler")
parser.add_argument("-s", "--start_date", dest="start_date", required=True, help="Start date (YYYY-MM-DD)")
parser.add_argument("-d", "--days", dest="days", type=int, default=1, help="Number of days to schedule (Default: 1)")
parser.add_argument("-t", "--time", dest="exec_time", default="17:00", help="Local time to execute daily task (Format HH:MM, Default: 17:00)")
args = parser.parse_args()

def run_scheduler():
    start_date_str = args.start_date
    num_days = args.days
    exec_time = args.exec_time
    
    obsplan_dir = directory.PLAN_DIR
    bat_file_path = directory.WORK_DIR / "run_solo.bat"
    
    # 1. Ensure the batch file exists for Task Scheduler
    if not bat_file_path.exists():
        print(f"⚠️ Warning: run_solo.bat not found at {bat_file_path}. Creating it now...")
        with open(bat_file_path, "w") as f:
            f.write("@echo off\n")
            f.write(f"cd {directory.WORK_DIR}\n")
            f.write("python mainobs.py -f %1\n")
        print("✅ Created run_solo.bat")

    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    except ValueError:
        print("❌ ERROR: Date format must be exactly 'YYYY-MM-DD'")
        sys.exit(1)

    print(f"\n--- Initiating Scheduler Queue for {num_days} Days ---")
    
    for i in range(num_days):
        current_dt = start_dt + timedelta(days=i)
        file_date_str = current_dt.strftime("%Y%m%d")
        
        yaml_filename = f"obsplan_{file_date_str}.yaml"
        yaml_path = obsplan_dir / yaml_filename
        
        print(f"\n[{i+1}/{num_days}] Scheduling for {current_dt.strftime('%Y-%m-%d')}:")
        
        # --- 2. Verify YAML File Exists ---
        if not yaml_path.exists():
            print(f"   ⚠️ WARNING: '{yaml_filename}' does NOT exist in {obsplan_dir}!")
            print("   -> Task will still be scheduled, but mainobs.py will abort if the file isn't uploaded before execution time.")
        else:
            print(f"   -> Found '{yaml_filename}'. Ready to schedule.")
        
        # --- 3. Queue in Windows Task Scheduler ---
        task_name = f"SOLO_{file_date_str}"
        task_date = current_dt.strftime("%Y/%m/%d") # Strictly formatted for Windows
        
        print(f"   -> Queuing Task Scheduler (Name: {task_name}, Time: {task_date} at {exec_time})")
        
        # Build the SchTasks command
        sch_cmd = [
            "SchTasks", 
            "/Create", 
            "/SC", "ONCE", 
            "/TN", task_name, 
            "/TR", f'"{bat_file_path}" {yaml_filename}', 
            "/SD", task_date, 
            "/ST", exec_time,
            "/F" 
        ]
        
        # Execute the command
        result = subprocess.run(sch_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("   ✅ Successfully registered with Windows Task Scheduler.")
        else:
            print(f"   ❌ FAILED to register task. Error: {result.stderr.strip()}")
            if "Access is denied" in result.stderr:
                print("   ⚠️ Administrator Privileges Required! Please run your terminal as Administrator.")
                sys.exit(1)

    print("\n--- Scheduler Queue Complete ---")
    print("You can verify your queued tasks by running: SchTasks /Query | findstr SOLO")

if __name__ == "__main__":
    run_scheduler()