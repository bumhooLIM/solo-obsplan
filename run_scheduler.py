import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent))
import directory

# --- Task Start Time ---
# Each task starts at this UT time on its plan's UT date, converted to this PC's local time,
# so daylight saving is handled automatically (01:00 UT = 18:00 PDT / 17:00 PST at SRO).
EXEC_UT = "01:00"

# --- Argparse Setting ---
parser = argparse.ArgumentParser(description="SOLO Scheduler: Queue existing YAML plans in Windows Task Scheduler")
parser.add_argument("-s", "--start_date", dest="start_date", required=True, help="UT Date of the FIRST plan file (YYYY-MM-DD)")
parser.add_argument("-d", "--days", dest="days", type=int, default=1, help="Number of days to schedule (Default: 1)")
parser.add_argument("-t", "--time", dest="exec_time", default=None, help="Optional override: local start time HH:MM on the local day before the UT plan date (Default: automatic, 01:00 UT in local time)")
args = parser.parse_args()

def run_scheduler():
    start_date_str = args.start_date
    num_days = args.days
    exec_time = args.exec_time
    
    obsplan_dir = directory.PLAN_DIR
    bat_file_path = directory.ROOT_DIR / "run_solo.bat"
    
    # 1. Ensure the batch file exists for Task Scheduler
    if not bat_file_path.exists():
        print(f"⚠️ Warning: run_solo.bat not found at {bat_file_path}. Creating it now...")
        with open(bat_file_path, "w") as f:
            f.write("@echo off\n")
            f.write(f"cd {directory.ROOT_DIR}\n")
            f.write("python mainobs.py -f %1\n")
        print("✅ Created run_solo.bat")

    try:
        # This is the UT date matching the filename
        start_ut_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    except ValueError:
        print("❌ ERROR: Date format must be exactly 'YYYY-MM-DD'")
        sys.exit(1)

    if exec_time:
        try:
            datetime.strptime(exec_time, "%H:%M")
        except ValueError:
            print("❌ ERROR: -t must be a local time in 'HH:MM' format")
            sys.exit(1)

    print(f"\n--- Initiating Scheduler Queue for {num_days} Days ---")
    if exec_time:
        print(f"Note: Tasks will start at {exec_time} local time, 1 local day prior to the UT plan date (manual -t).")
    else:
        print(f"Note: Tasks will start at {EXEC_UT} UT on the UT plan date, converted to this PC's local time.")
    
    for i in range(num_days):
        # UT date of the plan (filename and YYYY_MM folder)
        plan_ut_dt = start_ut_dt + timedelta(days=i)
        
        file_date_str = plan_ut_dt.strftime("%Y%m%d")

        # Extract the YYYY_MM formatted string for the new subdirectory structure
        sub_dir_str = plan_ut_dt.strftime("%Y_%m")

        yaml_filename = f"obsplan_{file_date_str}.yaml"
        yaml_rel_path = f"{sub_dir_str}/{yaml_filename}"
        
        # Target the file inside the new subdirectory structure
        yaml_path = obsplan_dir / sub_dir_str / yaml_filename

        print(f"\n[{i+1}/{num_days}] Target Plan: {yaml_rel_path} (UT: {plan_ut_dt.strftime('%Y-%m-%d')})")
        
        # --- 2. Verify YAML File Exists ---
        if not yaml_path.exists():
            print(f"   ⚠️ WARNING: '{yaml_filename}' does NOT exist in {obsplan_dir / sub_dir_str}!")
            print("   -> Task will still be scheduled, but mainobs.py will abort if the file isn't uploaded before execution time.")
        else:
            print(f"   -> Found '{yaml_filename}' in {sub_dir_str}.")
        
        # --- 3. Queue in Windows Task Scheduler ---
        task_name = f"SOLO_{file_date_str}"
        
        if exec_time: # Manual override: local time on the local day before the UT plan date
            hh, mm = map(int, exec_time.split(":"))
            exec_local_dt = (plan_ut_dt - timedelta(days=1)).replace(hour=hh, minute=mm).astimezone()
        else:         # Automatic: EXEC_UT on the UT plan date, converted to this PC's local time (handles DST)
            hh, mm = map(int, EXEC_UT.split(":"))
            exec_local_dt = plan_ut_dt.replace(hour=hh, minute=mm, tzinfo=timezone.utc).astimezone()

        task_date = exec_local_dt.strftime("%Y/%m/%d") # Windows requires Local Date
        task_time = exec_local_dt.strftime("%H:%M")    # Windows requires Local Time
        exec_ut_str = exec_local_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")

        print(f"   -> Queuing Task... (Executes LOCAL: {task_date} at {task_time} = {exec_ut_str} UT)")
        
        # Build the SchTasks command
        sch_cmd = [
            "SchTasks", 
            "/Create", 
            "/SC", "ONCE", 
            "/TN", task_name, 
            "/TR", f'"{bat_file_path}" "{yaml_rel_path}"',  # Passes 'YYYY_MM/obsplan_YYYYMMDD.yaml' to batch file
            "/SD", task_date,  # Local date
            "/ST", task_time,  # Local time
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
    print("Verify your queued tasks by running: SchTasks /Query | findstr SOLO")

if __name__ == "__main__":
    run_scheduler()