import sys
import time
import argparse
import yaml
from pathlib import Path
from alpaca.telescope import Telescope

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq = yaml.safe_load(file)
        
    # Apply the Alpaca networking fix (Address + Device Number)
    telescope_address = f"{eq['telescope']['ip']}:{eq['telescope']['port']}"
    telescope_device = eq['telescope']['device_number']
    T = Telescope(telescope_address, telescope_device)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to telescope ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-t", "--tracking", dest="switch", choices=['on', 'off'], required=True, help="Turn tracking 'on' or 'off'")
args = parser.parse_args()

switch = args.switch.lower()

def toggle_tracking():
    try:
        if switch == "on":
            # 1. Park Safety Check (Mounts refuse to track while parked)
            if getattr(T, 'AtPark', False):
                obs_logger.warning("FAIL: Mount is parked. You must unpark the mount before engaging tracking.")
                sys.exit(1)
            
            # 2. State Check
            if getattr(T, 'Tracking', False):
                obs_logger.info("Mount is already tracking.")
                sys.exit(0)

            # 3. Execution & Verification Buffer
            obs_logger.info("Engaging mount tracking...")
            T.Tracking = True
            time.sleep(2.0) # Hardware-to-software sync buffer

            if getattr(T, 'Tracking', False):
                obs_logger.info("SUCCESS : Tracking is ON.")
            else:
                obs_logger.error("FAIL : Mount refused to track (Check HUBO-i driver state).")
                sys.exit(1)

        elif switch == "off":
            # 1. State Check
            if not getattr(T, 'Tracking', False):
                obs_logger.info("Mount tracking is already OFF.")
                sys.exit(0)

            # 2. Execution & Verification Buffer
            obs_logger.info("Disabling mount tracking...")
            T.Tracking = False
            time.sleep(2.0) # Hardware-to-software sync buffer

            if not getattr(T, 'Tracking', False):
                obs_logger.info("SUCCESS : Tracking is OFF.")
            else:
                obs_logger.error("FAIL : Mount failed to stop tracking.")
                sys.exit(1)

    except Exception as e:
        obs_logger.error(f"FAIL : Tracking {switch.capitalize()} Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    toggle_tracking()