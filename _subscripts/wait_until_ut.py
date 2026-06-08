import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-u", "--ut", dest="ut", required=True, help="Target UT time (Format: HH:MM:SS)")
args = parser.parse_args()

def execute_wait():
    try:
        # 1. Parse the target time string (e.g., "14:30:00")
        try:
            target_time_obj = datetime.strptime(args.ut, "%H:%M:%S").time()
        except ValueError:
            obs_logger.error(f"FAIL: Invalid UT time format '{args.ut}'. Must be HH:MM:SS.")
            sys.exit(1)

        # 2. Get Current UTC Time
        now_utc = datetime.now(timezone.utc)
        
        # 3. Combine today's date with the target time
        target_utc = datetime.combine(now_utc.date(), target_time_obj).replace(tzinfo=timezone.utc)

        # 4. The Midnight Crossing Check
        # If the target time is earlier in the day than right now, it means tomorrow!
        if target_utc < now_utc:
            target_utc += timedelta(days=1)

        # Calculate total wait time
        wait_seconds = (target_utc - now_utc).total_seconds()
        
        # If we are already past the time (e.g., started the script late)
        if wait_seconds <= 0:
            obs_logger.info(f"Target UT ({args.ut}) has already passed. Proceeding immediately.")
            sys.exit(0)

        obs_logger.info(f"Pausing sequence. Waiting until {target_utc.strftime('%Y-%m-%d %H:%M:%S')} UT (Wait time: {wait_seconds/60:.1f} minutes).")

        # 5. The Wait Loop with a Heartbeat
        heartbeat_interval = 600  # Print a log message every 10 minutes (600 seconds)
        last_heartbeat = time.time()

        while True:
            current_utc = datetime.now(timezone.utc)
            if current_utc >= target_utc:
                break
            
            # Heartbeat logic to keep the log file active during long waits
            if time.time() - last_heartbeat > heartbeat_interval:
                remaining_mins = (target_utc - current_utc).total_seconds() / 60
                obs_logger.info(f"Status: Still waiting... ({remaining_mins:.1f} minutes remaining until {args.ut} UT).")
                last_heartbeat = time.time()
                
            time.sleep(1) # Check the clock every 1 second

        obs_logger.info(f"SUCCESS: Target UT ({args.ut}) reached. Resuming sequence.")

    except Exception as e:
        obs_logger.error(f"FAIL: Wait sequence encountered an error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    execute_wait()