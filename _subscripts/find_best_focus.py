import sys
import argparse
import numpy as np
import warnings
from pathlib import Path
from astropy.io import fits
from astropy.nddata import CCDData
from astropy.modeling import models, fitting
from astropy.utils.exceptions import AstropyUserWarning

# Suppress annoying Astropy warnings to keep the log clean
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter('ignore', category=RuntimeWarning)

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# Import your PSF analysis class (Adjust import to match your repo structure)
from solopy_pipeline import soloPSF 

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dir", dest="dir", required=True, help="Directory containing the focus FITS files")
args = parser.parse_args()

def find_best_focus():
    focus_dir = Path(args.dir)
    fits_files = list(focus_dir.glob("*.fits"))
    
    if not fits_files:
        obs_logger.error("FAIL: No FITS files found in focus directory.")
        sys.exit(1)
        
    focus_data = []
    
    # Initialize the spatial PSF analyzer
    psf_analyzer = soloPSF(init_fwhm=2.5, n_star=20)
    
    obs_logger.info("Extracting FWHM data from focus images...")
    
    for fpath in fits_files:
        try:
            # We extract the focus position directly from the filename (e.g., focus_35000.fits)
            pos_str = fpath.stem.split('_')[-1]
            foc_pos = int(pos_str)
            
            # Read image and process
            ccd = CCDData.read(fpath, unit='adu')
            df = psf_analyzer.process_ccd(ccd)
            
            if df.empty:
                obs_logger.warning(f"No valid stars found in {fpath.name}. Skipping.")
                continue
                
            # Get the median of the average FWHMs across all spatial regions
            overall_fwhm = df['fwhm_median'].median()
            
            if not np.isnan(overall_fwhm):
                focus_data.append((foc_pos, overall_fwhm))
                obs_logger.info(f" [Data Point] Focus: {foc_pos} | Overall FWHM: {overall_fwhm:.2f} px")
                
        except Exception as e:
            obs_logger.warning(f"Failed to process {fpath.name}: {e}")
            
    if len(focus_data) < 3:
        obs_logger.error("FAIL: Not enough valid focus points to fit a V-Curve (minimum 3 required).")
        sys.exit(1)
        
    # --- Fit the V-Curve (Inverted 1D Gaussian) ---
    focus_data = np.array(sorted(focus_data, key=lambda x: x[0]))
    x = focus_data[:, 0]
    y = focus_data[:, 1]
    
    # Generate intelligent initial guesses for the fitter
    baseline_guess = np.max(y)
    amplitude_guess = np.min(y) - baseline_guess  # Negative amplitude creates the "V" dip
    mean_guess = x[np.argmin(y)]
    stddev_guess = (np.max(x) - np.min(x)) / 4.0
    
    g_init = models.Const1D(amplitude=baseline_guess) + \
             models.Gaussian1D(amplitude=amplitude_guess, mean=mean_guess, stddev=stddev_guess)
             
    fitter = fitting.LevMarLSQFitter()
    g_fit = fitter(g_init, x, y)
    
    # The 'mean' of the Gaussian is our mathematical bottom of the V-Curve
    best_focus = g_fit[1].mean.value
    
    obs_logger.info(f"V-Curve Fit Complete. Mathematical Best Focus: {best_focus:.1f}")
    
    # Print exactly like this so mainobs.py can capture it
    print(f"BEST_FOCUS:{int(best_focus)}")

if __name__ == "__main__":
    find_best_focus()