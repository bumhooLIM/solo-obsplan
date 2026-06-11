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
    
    telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
    telescope_device = eq_config['telescope']['device_number']
    T = Telescope(telescope_address, telescope_device)
    
    # 1. Connection Verification
    if not getattr(T, 'Connected', False):
        obs_logger.warning("Mount driver is not connected. Attempting to connect now...")
        T.Connected = True
        time.sleep(2.0)
        if not getattr(T, 'Connected', False):
            raise Exception("Telescope driver refused connection via ASCOM/Alpaca.")
            
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to telescope ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--alt", dest="alt", type=float, required=True, help="Target Altitude in degrees (15 to 89)")
parser.add_argument("-z", "--az", dest="az", type=float, required=True, help="Target Azimuth in degrees (0 to 360)")
args = parser.parse_args()

def slew_altaz():
    try:
        alt = args.alt
        az = args.az

        # --- 2. Advanced Coordinate Safety Validation ---
        if not (0.0 <= az <= 360.0):
            obs_logger.error(f"FAIL: Azimuth ({az}) is out of bounds. Must be 0 to 360.")
            sys.exit(1)
            
        # Hard altitude floor to prevent pier/wall collisions
        if not (15.0 <= alt <= 88.0):
            obs_logger.error(f"FAIL: Altitude ({alt:.1f}°) is unsafe. Must be between 15° and 88° to protect mount.")
            sys.exit(1)
            
        # Protect against Meridian Flip confusion during Alt/Az slews
        if 170.0 <= az <= 190.0:
            obs_logger.error(f"FAIL: Target Azimuth ({az:.1f}°) crosses the Meridian. Alt/Az slewing aborted here to prevent mount flip errors.")
            sys.exit(1)

        obs_logger.info(f"Target Acquired -> ALT: {alt:.2f}° | AZ: {az:.2f}°")

        # --- 3. Hardware Prep & Sync Buffers ---
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before Alt/Az slew...")
            T.Unpark()
            
            while getattr(T, 'AtPark', True):
                time.sleep(1)
                
            obs_logger.info("Unpark complete. Waiting for HUBO-i driver state to sync...")
            time.sleep(3.0) 

        # --- 4. Safely Disengage Tracking ---
        if getattr(T, 'Tracking', True):
            obs_logger.info("Disabling stellar tracking for static Alt/Az slew...")
            T.Tracking = False
            time.sleep(2.0)
            
            # Verification check
            if getattr(T, 'Tracking', True):
                obs_logger.warning("Tracking failed to disengage! Attempting secondary override...")
                T.Tracking = False
                time.sleep(2.0)
                
            if getattr(T, 'Tracking', True):
                obs_logger.error("FATAL: Mount refuses to turn off tracking. Aborting Alt/Az slew.")
                sys.exit(1)
            else:
                obs_logger.info("SUCCESS: Tracking is OFF.")

        # --- 5. Driver Capability Check ---
        if not getattr(T, 'CanSlewAltAz', False):
            obs_logger.warning("Driver reports CanSlewAltAz is False. The command may be rejected by the ASCOM driver.")

        # --- 6. Asynchronous Slew & Polling Loop ---
        obs_logger.info("Slewing initiated. Waiting for mount to arrive...")
        T.SlewToAltAzAsync(az, alt)
        
        time.sleep(3.0) 
        
        timeout = 180 
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