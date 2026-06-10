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
        eq_config = yaml.safe_load(file)
    
    # Apply the Alpaca networking fix
    telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
    telescope_device = eq_config['telescope']['device_number']
    T = Telescope(telescope_address, telescope_device)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to telescope ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--alt", dest="alt", type=float, required=True, help="Target Altitude in degrees (0 to 90)")
parser.add_argument("-z", "--az", dest="az", type=float, required=True, help="Target Azimuth in degrees (0 to 360)")
args = parser.parse_args()

def slew_altaz():
    try:
        alt = args.alt
        az = args.az

        # --- 1. Basic Coordinate Validation ---
        if not (0.0 <= az <= 360.0):
            obs_logger.error(f"FAIL: Azimuth ({az}) is out of bounds. Must be 0 to 360.")
            sys.exit(1)
        if not (-90.0 <= alt <= 90.0):
            obs_logger.error(f"FAIL: Altitude ({alt}) is out of bounds. Must be -90 to 90.")
            sys.exit(1)

        obs_logger.info(f"Target Acquired -> ALT: {alt:.2f}° | AZ: {az:.2f}°")

        # --- 2. Hardware Prep & Sync Buffers ---
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before Alt/Az slew...")
            T.Unpark()
            
            # Wait for physical unpark
            while getattr(T, 'AtPark', True):
                time.sleep(1)
                
            # Hardware-to-software sync buffer (Fixes the HUBO-i "Ghost Slew" bug)
            obs_logger.info("Unpark complete. Waiting for HUBO-i driver state to sync...")
            time.sleep(3.0) 

        # ASCOM Standard: Tracking MUST be OFF to hold a static Alt/Az coordinate
        if getattr(T, 'Tracking', True):
            obs_logger.info("Disabling stellar tracking for static Alt/Az slew...")
            T.Tracking = False
            time.sleep(2.0) # Buffer to let the driver apply the tracking change

        # --- 3. Asynchronous Slew & Polling Loop ---
        obs_logger.info("Slewing initiated. Waiting for mount to arrive...")
        
        # NOTE: ASCOM signature requires (Azimuth, Altitude) in that specific order!
        T.SlewToAltAzAsync(az, alt)
        
        # Buffer to let the ASCOM driver register the moving state
        time.sleep(3.0) 
        
        timeout = 180 # 3 minutes max slew time
        start_time = time.time()
        
        while getattr(T, 'Slewing', False):
            if time.time() - start_time > timeout:
                obs_logger.error("TIMEOUT: Mount failed to reach Alt/Az target within 3 minutes.")
                try:
                    T.AbortSlew() 
                    obs_logger.warning("Emergency AbortSlew command sent to mount.")
                except:
                    pass
                sys.exit(1)
            time.sleep(1)
        
        obs_logger.info(f"SUCCESS : Mount successfully arrived at ALT: {alt:.2f}° | AZ: {az:.2f}°")

    except Exception as e:
        obs_logger.error(f"FAIL : Alt/Az Slewing Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    slew_altaz()