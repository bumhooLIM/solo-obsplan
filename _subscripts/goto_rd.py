import sys
import time
import argparse
import yaml
from pathlib import Path
from alpaca.telescope import Telescope
from astropy.coordinates import Angle
from astropy import units as u

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
import util
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    # 1. Load Equipment (Telescope IP/Port)
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq_config = yaml.safe_load(file)

    telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
    telescope_device = eq_config['telescope']['device_number']
    T = Telescope(telescope_address, telescope_device)

    # 2. Load Observatory Location (For safety checks)
    with open(directory.INFO_DIR / "observatory.yaml", 'r') as file:
        obs_config = yaml.safe_load(file)
    lat_str = str(obs_config['observatory']['latitude'])
    lon_str = str(obs_config['observatory']['longitude'])
    OBS_LAT = Angle(lat_str, unit=u.deg).deg
    OBS_LON = Angle(lon_str, unit=u.deg).deg
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration files ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--ra", dest="ra", required=True, help="Right Ascension (Hours or HH:MM:SS)")
parser.add_argument("-d", "--dec", dest="dec", required=True, help="Declination (Degrees or DD:MM:SS)")
args = parser.parse_args()

def slew_mount():
    try:
        # --- 1. Safely Parse Coordinates ---
        # Astropy Angle handles strings, decimals, and signs flawlessly
        ra_obj = Angle(args.ra, unit=u.hourangle)
        dec_obj = Angle(args.dec, unit=u.deg)
        
        # ASCOM requires RA in decimal hours and DEC in decimal degrees
        ra_hours = ra_obj.hour
        dec_deg = dec_obj.deg
        
        # Format beautiful strings for the log book
        ra_str = ra_obj.to_string(unit=u.hourangle, sep=':', precision=2, pad=True)
        dec_str = dec_obj.to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)

        obs_logger.info(f"Target Acquired -> RA: {ra_str} | DEC: {dec_str}")

        # --- 2. Redundant Hardware Safety Check ---
        # Evaluates safety even if run manually from the terminal
        alt, az = util.equatorial2horizon(ra_hours, dec_deg, latitude=OBS_LAT, longitude=OBS_LON, t="now")
        if alt <= 15.0:
            obs_logger.error(f"FAIL: Target is too low (Alt: {alt:.1f}°). Slewing aborted to protect mount.")
            sys.exit(1)
        if 170.0 <= az <= 190.0:
            obs_logger.error(f"FAIL: Target is crossing the meridian (Az: {az:.1f}°). Slewing aborted.")
            sys.exit(1)

        # --- 3. Pre-Slew Preparation ---
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before slew...")
            T.Unpark()
            # Wait for physical unpark to complete
            while getattr(T, 'AtPark', True):
                time.sleep(1)
        
        if not getattr(T, 'Tracking', False):
            T.Tracking = True

        # --- 4. Asynchronous Slew & Polling Loop ---
        obs_logger.info("Slewing initiated. Waiting for mount to arrive...")
        T.SlewToCoordinatesAsync(ra_hours, dec_deg)
        
        # Tiny buffer to let the ASCOM driver register the "Slewing=True" state
        time.sleep(2) 
        
        timeout = 180 # Maximum 3 minutes for a slew across the entire sky
        start_time = time.time()
        
        # Polling loop: Wait until the telescope stops moving
        while getattr(T, 'Slewing', False):
            if time.time() - start_time > timeout:
                obs_logger.error(f"TIMEOUT: Mount failed to reach target within {timeout} seconds.")
                try:
                    T.AbortSlew() # Emergency stop
                    obs_logger.warning("Emergency AbortSlew command sent to mount.")
                except:
                    pass
                sys.exit(1)
            time.sleep(5) # Check every 5 seconds
        
        obs_logger.info(f"SUCCESS : Mount successfully arrived at RA: {ra_str} | DEC: {dec_str}")

    except Exception as e:
        obs_logger.error(f"FAIL : Slewing Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    slew_mount()