import sys
import argparse
import subprocess
import yaml
import time
from pathlib import Path

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as f:
        eq = yaml.safe_load(f)
        
    CLEWARE_EXE = str(eq['mount_power']['exe_path'])
    CLEWARE_SN = str(eq['mount_power']['serial'])
except Exception as e:
    obs_logger.error(f"FAIL: Could not load Cleware configuration: {e}")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", choices=['on', 'off'], required=True)
args = parser.parse_args()

# The flag file used to communicate with the background process
LOCK_FILE = directory.INFO_DIR / "mount_power.lock"

def ping_switch(state_flag):
    """Silently fires the command to the switch."""
    try:
        subprocess.run([CLEWARE_EXE, "-n", CLEWARE_SN, state_flag], capture_output=True, check=True)
    except Exception:
        pass # Suppressed to avoid spamming the log file every 1 second

if args.switch == "on":
    obs_logger.info("Engaging Mount Power (Hardware Watchdog Active)...")
    
    # Write the "ON" flag to the file
    with open(LOCK_FILE, "w") as f:
        f.write("ON")

    # --- THE DAEMON LOOP ---
    # This loop keeps the script alive in the background, pinging the switch
    while True:
        try:
            with open(LOCK_FILE, "r") as f:
                current_state = f.read().strip()
            
            # If mainobs.py changes this file to "OFF", break the loop
            if current_state != "ON":
                break
        except Exception:
            break # If the file is accidentally deleted, fail-safe and turn off

        # Ping the switch to beat the 2-second hardware timer
        ping_switch("1")
        time.sleep(10) # Cleware has a built-in 60-second watchdog, so we ping every 10 seconds to be safe

    # When the loop breaks, send the final OFF command and exit
    ping_switch("0")
    obs_logger.info("SUCCESS : Watchdog daemon cleanly terminated. Mount power cut.")

elif args.switch == "off":
    obs_logger.info("Signaling Watchdog Daemon to cut Mount Power...")
    
    # Tell the background loop to stop
    with open(LOCK_FILE, "w") as f:
        f.write("OFF")
        
    # Send a redundant OFF signal instantly just to be safe
    ping_switch("0")