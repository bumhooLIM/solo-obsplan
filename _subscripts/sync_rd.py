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
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq_config = yaml.safe_load(file)
    
    # Apply the Alpaca networking fix (Address + Device Number)
    telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
    telescope_device = eq_config['telescope']['device_number']
    T = Telescope(telescope_address, telescope_device)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to telescope ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--ra", dest="ra", required=True, help="Solved Right Ascension (Hours or HH:MM:SS)")
parser.add_argument("-d", "--dec", dest="dec", required=True, help="Solved Declination (Degrees or DD:MM:SS)")
args = parser.parse_args()

def execute_sync():
    try:
        # --- 1. Coordinate Parsing & Validation ---
        try:
            # Safely parse whatever format the plate solver spits out into strict Hours and Degrees
            ra_obj = Angle(args.ra, unit=u.hourangle)
            dec_obj = Angle(args.dec, unit=u.deg)
            ra_hours = ra_obj.hour
            dec_deg = dec_obj.deg
            
            ra_str = ra_obj.to_string(unit=u.hourangle, sep=':', precision=2, pad=True)
            dec_str = dec_obj.to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)
        except Exception as e:
            obs_logger.error(f"FAIL: Coordinate format error. Could not parse RA: {args.ra} or DEC: {args.dec} ({e})")
            sys.exit(1)

        obs_logger.info(f"Initiating Mount Sync -> Plate Solved Coordinates: RA {ra_str} | DEC {dec_str}")

        # --- 2. Hardware Capability Check ---
        if not getattr(T, 'CanSync', False):
            obs_logger.error("FAIL: This mount does not support software coordinate syncing.")
            sys.exit(1)

        # --- 3. Safely Prepare the Mount ---
        # A mount must be unparked and tracking to accept a Sync command
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before syncing...")
            T.Unpark()
            while getattr(T, 'AtPark', True):
                time.sleep(1)
            time.sleep(3.0) # Hardware-to-software sync buffer
            
        if not getattr(T, 'Tracking', False):
            obs_logger.info("Engaging tracking before sync...")
            T.Tracking = True
            time.sleep(2.0)
            if not getattr(T, 'Tracking', False):
                obs_logger.error("FAIL: Mount refused to track. Cannot sync.")
                sys.exit(1)

        # --- 4. Execute the Sync ---
        obs_logger.info("Sending Sync command to mount internal model...")
        T.SyncToCoordinates(ra_hours, dec_deg)
        
        # Brief buffer to allow the mount to update its internal encoders
        time.sleep(1.0)
        
        # --- 5. Verification ---
        # We query the mount to see if its current reported position matches what we just sent
        current_ra = getattr(T, 'RightAscension', 0.0)
        current_dec = getattr(T, 'Declination', 0.0)
        
        # Check if the mount's reported RA/DEC is within a tiny fraction of what we sent
        if abs(current_ra - ra_hours) < 0.01 and abs(current_dec - dec_deg) < 0.1:
            obs_logger.info("SUCCESS : Mount successfully synced to plate-solved coordinates.")
        else:
            obs_logger.warning(f"Mount synced, but reported coordinates (RA:{current_ra:.2f}, DEC:{current_dec:.2f}) slightly differ from input. Check J2000/JNOW epoch settings.")

    except Exception as e:
        obs_logger.error(f"FAIL: Sync sequence encountered an error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    execute_sync()