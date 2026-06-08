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

# --- Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq_config = yaml.safe_load(file)
    
    telescope_ip = eq_config['telescope']['ip']
    telescope_port = eq_config['telescope']['port']
    T = Telescope(telescope_ip, telescope_port)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-c", "--command", dest="command", action="store", choices=['home'], required=True, help="Command to 'home' the mount")
args = parser.parse_args()

def execute_homing():
    try:
        # 1. Hardware Capability Check
        if not getattr(T, 'CanFindHome', False):
            obs_logger.error("FAIL: This mount does not support software homing (CanFindHome = False).")
            sys.exit(1)

        # 2. Check if already at Home
        if getattr(T, 'AtHome', False):
            obs_logger.info("Mount is already at the Home position.")
            sys.exit(0)

        # 3. Unpark Check (Most mounts will reject FindHome if Parked)
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before homing...")
            T.Unpark()
            # Wait for physical unpark to complete
            while getattr(T, 'AtPark', True):
                time.sleep(1)

        # 4. Initiate Homing Sequence
        obs_logger.info("Homing initiated. Waiting for mount to find index sensors...")
        T.FindHome()

        # Brief buffer to let the ASCOM driver register the moving state
        time.sleep(2)

        # 5. The Safety Polling Loop
        timeout = 180 # 3 minutes max (homing can require a full 360-degree rotation)
        start_time = time.time()
        
        # Loop until the mount reports it has successfully hit the home sensors
        while not getattr(T, 'AtHome', False):
            if time.time() - start_time > timeout:
                obs_logger.error(f"TIMEOUT: Mount failed to find home within {timeout} seconds.")
                try:
                    T.AbortSlew() # Emergency brake
                    obs_logger.warning("Emergency AbortSlew command sent to mount.")
                except:
                    pass
                sys.exit(1)
            time.sleep(1)

        obs_logger.info("SUCCESS: Mount successfully homed and encoders re-synced.")

    except Exception as e:
        obs_logger.error(f"FAIL: Homing Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    if args.command.lower() == "home":
        execute_homing()