import sys
import time
import argparse
import yaml
import subprocess
from pathlib import Path
from alpaca.telescope import Telescope
from astropy.coordinates import Angle
from astropy import units as u
from astropy.coordinates import Angle, EarthLocation, AltAz, get_sun
from astropy.time import Time

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
import util
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq_config = yaml.safe_load(file)
    
    telescope_address = f"{eq_config['telescope']['ip']}:{eq_config['telescope']['port']}"
    T = Telescope(telescope_address, eq_config['telescope']['device_number'])

    with open(directory.INFO_DIR / "observatory.yaml", 'r') as file:
        obs_config = yaml.safe_load(file)
        
    lat_str = str(obs_config['observatory']['latitude'])
    lon_str = str(obs_config['observatory']['longitude'])
    OBS_LAT = Angle(lat_str, unit=u.deg).deg
    OBS_LON = Angle(lon_str, unit=u.deg).deg
    # OBS_ELEV = obs_config['observatory']['elevation']
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration files ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--ra", dest="ra", required=True)
parser.add_argument("-d", "--dec", dest="dec", required=True)
args = parser.parse_args()

def is_dawn(lat, lon):
    """Returns True if the Sun is above -10 degrees altitude (Nautical Twilight)"""
    loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
    now = Time.now()
    sun = get_sun(now).transform_to(AltAz(obstime=now, location=loc))
    return sun.alt.deg > -10.0

def check_roof_open():
    """Silently runs the roof checker script. Returns True if Open, False if Closed/Error."""
    # We suppress the output so we don't spam the log file every 60 seconds
    result = subprocess.run(
        [sys.executable, str(directory.SCRIPT_DIR / "check_roof_status.py")], 
        capture_output=True
    )
    return result.returncode == 0

def slew_mount():
    try:
        # --- 1. Parse Coordinates ---
        ra_obj = Angle(args.ra, unit=u.hourangle)
        dec_obj = Angle(args.dec, unit=u.deg)
        ra_hours = ra_obj.hour
        dec_deg = dec_obj.deg
        ra_str = ra_obj.to_string(unit=u.hourangle, sep=':', precision=2, pad=True)
        dec_str = dec_obj.to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)

        obs_logger.info(f"Target Acquired -> RA: {ra_str} | DEC: {dec_str}")

        # --- 2. Hardware Safety Check ---
        alt, az = util.equatorial2horizon(ra_hours, dec_deg, latitude=OBS_LAT, longitude=OBS_LON, t="now")
        if alt <= 15.0:
            obs_logger.error(f"FAIL: Target is too low (Alt: {alt:.1f}°). Slewing aborted to protect mount.")
            sys.exit(1)
        if 170.0 <= az <= 190.0:
            obs_logger.error(f"FAIL: Target is crossing the meridian (Az: {az:.1f}°). Slewing aborted.")
            sys.exit(1)

        # --- 3. WEATHER WAIT LOOP ---
        max_wait_time = 7200  # 2 Hours in seconds
        wait_start = time.time()
        heartbeat = 1800       # Print a log message every 30 minutes
        last_heartbeat = time.time()

        if not check_roof_open():
            obs_logger.warning("Roof is CLOSED. Entering weather standby mode...")
            
            # CRITICAL SAFETY: Ensure mount is parked while waiting out the storm
            if not getattr(T, 'AtPark', False):
                obs_logger.info("Parking mount to secure telescope during weather delay...")
                T.Park()
                while not getattr(T, 'AtPark', False):
                    time.sleep(1)

            # Polling Loop for the Roof
            while True:
                if check_roof_open():
                    obs_logger.info("Roof has RE-OPENED! Resuming observation sequence.")
                    break
                
                # Check 1: Dawn / Sunrise
                if is_dawn(OBS_LAT, OBS_LON):
                    obs_logger.error("DAWN DETECTED: The sun is rising. Aborting weather wait.")
                    sys.exit(2) # Exit Code 2 = Dawn Abort
                
                # Check 2: Timeout
                if time.time() - wait_start > max_wait_time:
                    obs_logger.error(f"TIMEOUT: Roof remained closed for over {max_wait_time/60:.0f} minutes.")
                    sys.exit(3) # Exit Code 3 = Global Weather Abort
                
                # Heartbeat Logging
                if time.time() - last_heartbeat > heartbeat:
                    remaining = (max_wait_time - (time.time() - wait_start)) / 60
                    obs_logger.info(f"Status: Still waiting for clear weather... (Timeout in {remaining:.0f} mins)")
                    last_heartbeat = time.time()
                
                time.sleep(600) # Ping the roof status every 600 seconds

        # --- 4. Pre-Slew Preparation (With Sync Buffers) ---
        if getattr(T, 'AtPark', False):
            obs_logger.info("Mount is parked. Unparking before slew...")
            T.Unpark()
            
            # Wait for physical unpark
            while getattr(T, 'AtPark', True):
                time.sleep(1)
                
            # CRITICAL FIX: The Hardware-to-Software Sync Buffer
            # Give the HUBO-i Windows UI 3 seconds to register that the mount is no longer parked.
            obs_logger.info("Unpark complete. Waiting for HUBO-i driver state to sync...")
            time.sleep(3.0) 
        
        # --- Safely Engage Tracking ---
        if not getattr(T, 'Tracking', False):
            obs_logger.info("Engaging mount tracking...")
            T.Tracking = True
            time.sleep(3.0) # Give driver time to apply tracking
            
            # Verification check to ensure the driver accepted the command
            if not getattr(T, 'Tracking', False):
                obs_logger.warning("Tracking failed to engage! Attempting secondary override...")
                T.Tracking = True
                time.sleep(3.0)
                
            if getattr(T, 'Tracking', False):
                obs_logger.info("SUCCESS : Tracking is ON.")
            else:
                obs_logger.error("FATAL : Mount refuses to track. Aborting slew.")
                sys.exit(1)

        # --- 5. Asynchronous Slew & Polling Loop ---
        obs_logger.info("Slewing initiated. Waiting for mount to arrive...")
        T.SlewToCoordinatesAsync(ra_hours, dec_deg)
        
        # Buffer to let the ASCOM driver register the moving state
        time.sleep(3.0) 
        
        timeout = 180 
        start_time = time.time()
        
        while getattr(T, 'Slewing', False):
            if time.time() - start_time > timeout:
                obs_logger.error("TIMEOUT: Mount failed to reach target within 3 minutes.")
                try:
                    T.AbortSlew() 
                    obs_logger.warning("Emergency AbortSlew command sent to mount.")
                except:
                    pass
                sys.exit(1)
            time.sleep(1)
        
        obs_logger.info(f"SUCCESS : Mount successfully arrived at RA: {ra_str} | DEC: {dec_str}")

    except Exception as e:
        obs_logger.error(f"FAIL : Slewing Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    slew_mount()