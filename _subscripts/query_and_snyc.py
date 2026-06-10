import sys
import time
import argparse
import numpy as np
import yaml
from pathlib import Path
from astropy.io import fits
from astropy.coordinates import Angle
import astropy.units as u

import sep
import astrometry
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
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to telescope ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-f", "--file", dest="file", required=True, help="Path to the FITS file to solve")
args = parser.parse_args()

def query_and_sync():
    fpath_fits = Path(args.file)
    
    if not fpath_fits.exists():
        obs_logger.error(f"FAIL: The FITS file {fpath_fits.name} does not exist.")
        sys.exit(1)

    obs_logger.info(f"Initiating Query & Sync Sequence for: {fpath_fits.name}")

    # ==========================================
    # PART 1: IN-MEMORY PLATE SOLVING
    # ==========================================
    try:
        with fits.open(fpath_fits) as hdul:
            data = hdul[0].data.astype(np.float32)
            header = hdul[0].header
            
            ra_hint = header.get("RA", 0.0)
            dec_hint = header.get("DEC", 0.0)
            height, width = data.shape
    except Exception as e:
        obs_logger.error(f"FAIL: Error reading FITS file ({e})")
        sys.exit(1)

    try:
        bkg = sep.Background(data)
        objs = sep.extract(data - bkg.back(), thresh=3.0 * bkg.globalrms, minarea=5)
        bright = objs[np.argsort(objs['flux'])[::-1][:50]]
        coords = np.vstack((bright['x'], bright['y'])).T
    except Exception as e:
        obs_logger.error(f"FAIL: Source extraction failed. Image might be blank ({e})")
        sys.exit(1)

    wcs_solved = False
    best_match = None
    cache_dir = directory.INFO_DIR / "astrometry_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        with astrometry.Solver(
            astrometry.series_4100.index_files(cache_directory=str(cache_dir), scales={8, 9, 10})
        ) as solver:
            sol = solver.solve(
                stars=coords,
                size_hint=astrometry.SizeHint(lower_arcsec_per_pixel=2.90, upper_arcsec_per_pixel=3.00),
                position_hint=astrometry.PositionHint(
                    ra_deg=ra_hint, dec_deg=dec_hint, radius_deg=2.0
                ),
                solution_parameters=astrometry.SolutionParameters(
                    logodds_callback=lambda l: astrometry.Action.STOP if len(l) >= 10 else astrometry.Action.CONTINUE,
                    sip_order=3
                )
            )
            
            if sol.has_match():
                best_match = sol.best_match()
                wcs_solved = True
                obs_logger.info(f"WCS Match Found! (Scale: {best_match.scale_arcsec_per_pixel:.2f} arcsec/pixel)")
            else:
                obs_logger.error("FAIL: No WCS solution found for this field.")
                sys.exit(1)
                
    except Exception as e:
        obs_logger.error(f"FAIL: Astrometry.net solver crashed ({e})")
        sys.exit(1)

    # ==========================================
    # PART 2: MOUNT SYNCING
    # ==========================================
    if wcs_solved and best_match:
        try:
            wcs = best_match.astropy_wcs()
            center_x, center_y = width / 2.0, height / 2.0
            sky_center = wcs.pixel_to_world(center_x, center_y)
            
            ra_deg = sky_center.ra.deg
            dec_deg = sky_center.dec.deg

            # ASCOM expects Right Ascension in Hours!
            ra_hours = Angle(ra_deg, unit=u.deg).hour
            
            # Format strings for the logger
            ra_str = Angle(ra_deg, unit=u.deg).to_string(unit=u.hour, sep=':', precision=2, pad=True)
            dec_str = Angle(dec_deg, unit=u.deg).to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)

            obs_logger.info(f"Target mathematically confirmed at RA: {ra_str} | DEC: {dec_str}")

            # --- Hardware Capability Check ---
            if not getattr(T, 'CanSync', False):
                obs_logger.error("FAIL: Mount does not support software coordinate syncing.")
                sys.exit(1)

            # --- Safely Prepare the Mount ---
            if getattr(T, 'AtPark', False):
                obs_logger.info("Mount is parked. Unparking before syncing...")
                T.Unpark()
                while getattr(T, 'AtPark', True):
                    time.sleep(1)
                time.sleep(3.0) 
                
            if not getattr(T, 'Tracking', False):
                obs_logger.info("Engaging tracking before sync...")
                T.Tracking = True
                time.sleep(2.0)
                if not getattr(T, 'Tracking', False):
                    obs_logger.error("FAIL: Mount refused to track. Cannot sync.")
                    sys.exit(1)

            # --- Execute the Sync ---
            obs_logger.info("Sending Sync command to mount internal model...")
            T.SyncToCoordinates(ra_hours, dec_deg)
            time.sleep(1.0)
            
            # --- Verification ---
            current_ra = getattr(T, 'RightAscension', 0.0)
            current_dec = getattr(T, 'Declination', 0.0)
            
            if abs(current_ra - ra_hours) < 0.01 and abs(current_dec - dec_deg) < 0.1:
                obs_logger.info("SUCCESS : Mount perfectly synced to plate-solved coordinates.")
                sys.exit(0)
            else:
                obs_logger.warning(f"Mount synced, but reported coords (RA:{current_ra:.2f}, DEC:{current_dec:.2f}) slightly differ. (Possible J2000 vs JNOW epoch mismatch)")
                sys.exit(0) # We still exit with 0 (Success) because the command was sent successfully
                
        except Exception as e:
            obs_logger.error(f"FAIL: Hardware sync sequence encountered an error ({e})")
            sys.exit(1)

if __name__ == "__main__":
    query_and_sync()