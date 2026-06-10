import sys
import time
import argparse
import yaml
from pathlib import Path
from alpaca.telescope import Telescope

# --- Connect to Root Directory ---
# Appends 'solo-obsplan' to the system path, allowing imports from root
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
config_file = directory.INFO_DIR / "equipment.yaml"

with open(config_file, 'r') as file:
    eq_config = yaml.safe_load(file)

telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
telescope_device = eq_config['telescope']['device_number']
T = Telescope(telescope_address, telescope_device)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-p", "--parking", dest="command", action="store", required=True, help="Command to 'park' or 'unpark'")
args = parser.parse_args()

command = args.command.lower()

# ======= Main Commands ======= #
if command == "park":
    try:
        # Check if the telescope is already parked
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is already parked.")
        else:
            T.Park()
            obs_logger.info("Parking initiated. Waiting for mount...")
        
            # Polling loop to ensure physical parking is complete
            timeout = 60
            start_time = time.time()
            while not getattr(T, 'AtPark', False):
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Mount failed to park within {timeout} seconds.")
                time.sleep(1)
           
            obs_logger.info("Successfully parked telescope.")
            time.sleep(5)
    
    except Exception as e:
        obs_logger.error(f"FAIL : Park telescope. Error: {str(e)}")

elif command == "unpark":
    try:
        if not getattr(T, 'AtPark', False):
            obs_logger.info("Mount is already unparked.")
        else:
            T.Unpark()
            obs_logger.info("Unparking initiated. Waiting for mount...")
            
            # Polling loop with a 30-second timeout
            timeout = 30
            start_time = time.time()
            while getattr(T, 'AtPark', False):
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Mount failed to unpark within {timeout} seconds.")
                time.sleep(1)

            obs_logger.info("Successfully unparked telescope.")
            time.sleep(5)
    
    except Exception as e:
        obs_logger.error(f"FAIL : Unpark telescope. Error: {str(e)}")

else:
    obs_logger.warning(f"Unrecognized parking command: '{command}'. Use 'park' or 'unpark'.")