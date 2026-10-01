import sys
import argparse
import time
import subprocess
import yaml
from pathlib import Path
import numpy as np
import astropy.io.fits as fits
from astropy.time import Time
from astropy import units as u

from alpaca.camera import Camera
from alpaca.telescope import Telescope
from alpaca.focuser import Focuser

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
import util
from logger import obs_logger

# --- Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as f:
        eq = yaml.safe_load(f)
    with open(directory.INFO_DIR / "observatory.yaml", 'r') as f:
        obs = yaml.safe_load(f)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load YAML configurations: {e}")
    sys.exit(1)

t_addr = f"{eq['telescope']['ip']}:{eq['telescope']['port']}"
c_addr = f"{eq['camera']['ip']}:{eq['camera']['port']}"
f_addr = f"{eq['focuser']['ip']}:{eq['focuser']['port']}"

# Initialize Hardware
T = Telescope(t_addr, eq['telescope']['device_number'])
C = Camera(c_addr, eq['camera']['device_number'])
F = Focuser(f_addr, eq['focuser']['device_number'])

# --- Argparse ---
parser = argparse.ArgumentParser()
parser.add_argument("-n", "--name", required=True)
parser.add_argument("-t", "--time", type=float, required=True)
parser.add_argument("-i", "--iter", type=int, default=1)
parser.add_argument("-x", "--xbin", type=int, default=1)
parser.add_argument("-y", "--ybin", type=int, default=1)
parser.add_argument("-m", "--mode", type=str, default="light", choices=["light", "dark", "bias"], help="Frame type")
parser.add_argument("--output_dir", type=str, default=str(directory.DATA_DIR), help="Directory to save FITS files")
parser.add_argument("--min_alt", type=float, default=None, help="Targeted observations: stop once the pointing drops to this altitude [deg] (needs --ra/--dec)")
parser.add_argument("--ra", type=str, default=None, help="Pointing RA (HH:MM:SS) for --min_alt")
parser.add_argument("--dec", type=str, default=None, help="Pointing Dec (DD:MM:SS) for --min_alt")
args = parser.parse_args()

# --- Targeted Sequence Stops (only with --min_alt) ---
ROOF_CHECK_EVERY = 10 # Re-check the roof every N frames during a targeted sequence

if args.min_alt is not None and (args.ra is None or args.dec is None):
    obs_logger.error("FAIL: --min_alt needs --ra and --dec to compute the pointing altitude.")
    sys.exit(1)

OBS_LAT = util.degree2float(str(obs['observatory']['latitude']))
OBS_LON = util.degree2float(str(obs['observatory']['longitude']))
OBS_ELEV = float(obs['observatory'].get('elevation', 1400))

def open_ds9(img_path):
    """Safely handles opening DS9."""
    ds9_path = str(eq.get('ds9', {}).get('path', r"C:\SAOImageDS9\ds9.exe"))
    ds9_exe = str(eq.get('ds9', {}).get('exe', "ds9.exe"))
    try:
        subprocess.run(["taskkill", "/IM", ds9_exe, "/F"], capture_output=True)
        subprocess.Popen([ds9_path, str(img_path), "-geometry", "600x600+1100+0", "-zoom", "to", "fit"])
    except Exception as e:
        obs_logger.warning(f"Could not open DS9: {e}")

def safe_get(device, property_name, default="NaN"):
    """Fetches telemetry safely. Returns default if device drops connection."""
    try:
        return getattr(device, property_name)
    except Exception:
        return default

# --- Exposure Sequence ---
try:
    if not C.Connected:
        obs_logger.error("FAIL: Camera is not connected. Check ASCOM Server.")
        sys.exit(1)

    # Ensure output directory exists before shooting
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Determine Mode Settings
    is_light = True if args.mode.lower() == "light" else False
    exptime = 0.01 if args.mode.lower() == "bias" else args.time
    imagetyp = args.mode.capitalize() # "Light", "Dark", or "Bias"
    
    obs_logger.info(f"Starting Sequence: {args.name} | {exptime}s x {args.iter}")

    for i in range(args.iter):
        # 0. Targeted sequences: stop once the pointing drops to --min_alt, or if the roof closes
        if args.min_alt is not None:
            try:
                alt, _ = util.equatorial2horizon(args.ra, args.dec, latitude=OBS_LAT*u.deg, longitude=OBS_LON*u.deg, height=OBS_ELEV*u.m, t="now")
            except Exception as e:
                obs_logger.error(f"FAIL: Altitude check failed ({e}). Stopping {args.name} for safety after {i} frame(s).")
                break

            if alt <= args.min_alt:
                obs_logger.info(f"Altitude limit reached for {args.name} (Alt: {alt:.1f}° <= {args.min_alt:.0f}°). Stopping sequence after {i} frame(s).")
                break

            if i > 0 and i % ROOF_CHECK_EVERY == 0:
                roof_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "check_roof_status.py")], capture_output=True)
                if roof_proc.returncode != 0:
                    obs_logger.error(f"Roof is not OPEN. Stopping {args.name} after {i} frame(s).")
                    break

        try:
            # 1. Check if camera is busy from a previous glitch (State 0 = Idle)
            # ASCOM CameraState enum: 0=Idle, 1=Waiting, 2=Exposing, 3=Reading, 4=Download, 5=Error
            if C.CameraState != 0:
                obs_logger.warning("Camera not Idle. Waiting for buffer to clear...")
                time.sleep(2)

            # 2. Configure Camera
            C.BinX = args.xbin
            C.BinY = args.ybin
            C.StartX = 0
            C.StartY = 0
            C.NumX = C.CameraXSize // args.xbin
            C.NumY = C.CameraYSize // args.ybin
        
            # 3. Start Exposure
            start_time_iso = Time.now().iso
            C.StartExposure(exptime, is_light)
            
            # 4. Safely Poll with Timeout Buffer (Exposure time + 60s for download)
            timeout = exptime + 60
            start_wait = time.time()
            
            while not C.ImageReady:
                if time.time() - start_wait > timeout:
                    raise TimeoutError(f"Camera hang detected. ImageReady = False after {timeout}s.")
                time.sleep(1)
                
            # Calculate timing data right after shutter closes/download finishes
            end_time = Time.now()
            end_time_iso = end_time.iso
            local_time = time.localtime(end_time.unix)
            jd = end_time.jd
            
            # 5. Get Data
            img = C.ImageArray
            nda = np.array(img, dtype=np.uint16).transpose()
            
            # --- 5b. FITS Standard Coordinate Formatting ---
            raw_ra = safe_get(T, "RightAscension")
            raw_dec = safe_get(T, "Declination")
            raw_alt = safe_get(T, "Altitude")
            raw_az = safe_get(T, "Azimuth")
            
            # Convert ASCOM outputs to FITS-compliant string formats (if connection is alive)
            fits_ra = util.float2hour(raw_ra) if raw_ra != "NaN" else "NaN"
            fits_dec = util.float2degree(raw_dec) if raw_dec != "NaN" else "NaN"
            fits_alt = util.float2degree(raw_alt) if raw_alt != "NaN" else "NaN"
            fits_az = util.float2degree(raw_az) if raw_az != "NaN" else "NaN"
            
            # 6. Create FITS Header (Safely fetching ancillary hardware data)
            hdr = fits.Header()
            
            # Core Timing 
            hdr["DATE-OBS"] = start_time_iso
            hdr["UTC-STA"] = start_time_iso
            hdr["UTC-END"] = end_time_iso
            hdr["LT"] = time.strftime('%Y-%m-%d %H:%M:%S', local_time)
            hdr["JD"] = jd
            
            # Observation Params
            hdr["OBJECT"] = args.name
            hdr["IMAGETYP"] = imagetyp
            hdr["EXPTIME"] = exptime
            hdr["XBINNING"] = args.xbin
            hdr["YBINNING"] = args.ybin
            hdr["CCDTEMP"] = safe_get(C, "CCDTemperature")
            hdr["FILTER"] = "CLEAR"
            
            # Mount Coordinates
            hdr["RA"] = fits_ra       # Formatted as HH:MM:SS
            hdr["DEC"] = fits_dec     # Formatted as DD:MM:SS
            hdr["ALT"] = fits_alt     # Formatted as DD:MM:SS
            hdr["AZ"] = fits_az       # Formatted as DD:MM:SS
            
            # Optics
            hdr["FOCUS"] = safe_get(F, "Position")
            hdr["FOCALLEN"] = eq['telescope']['focal_length']
            hdr["APDIA"] = eq['telescope']['diameter']
            hdr["PIXSZ"] = eq['camera']['pixel_size']
            
            # Site & Observer Info
            hdr["OBSERVAT"] = obs['observatory']['name']
            hdr["LON"] = obs['observatory']['longitude']
            hdr["LAT"] = obs['observatory']['latitude']
            hdr["ELEVAT"] = obs['observatory'].get('elevation', 'NaN')
            hdr["OBSERVER"] = "Bumhoo LIM"
            
            # 7. Save File
            filename = f"{args.name}_{i+1:03d}_{time.strftime('%Y%m%d%H%M%S')}.fits"
            filepath = output_path / filename
            fits.PrimaryHDU(nda, header=hdr).writeto(filepath, overwrite=True)
            
            obs_logger.info(f"Saved {filename} | Median: {np.median(nda):.0f} | Min: {np.min(nda)} | Max: {np.max(nda)}")
            open(directory.INFO_DIR / "prev_img.txt", "w").write(str(filepath))
        
            open_ds9(filepath)

        except Exception as e:
            # By catching errors inside the loop, one bad frame won't abort the whole sequence
            obs_logger.error(f"Error on frame {i+1}/{args.iter}: {e}")
            obs_logger.info("Attempting to recover for next frame...")
            time.sleep(2) # Brief pause to let hardware reset before trying next iteration

except Exception as e:
    obs_logger.error(f"Fatal sequence error: {e}")
    sys.exit(1)