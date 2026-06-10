# --- TOP IMPORTS (Notice photutils is completely gone) ---
import sys
import argparse
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

# Astropy & SEP
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.modeling import models, fitting
from astropy.modeling.models import Gaussian2D
from astropy.utils.exceptions import AstropyUserWarning
import sep

# Suppress annoying Astropy warnings
warnings.simplefilter('ignore', category=AstropyUserWarning)
warnings.simplefilter('ignore', category=RuntimeWarning)

# --- (Directory/Logger setup remains here) ---

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# ======================================================================
# STANDALONE PSF ANALYZER (Replaces solopy.soloPSF)
# ======================================================================
class StandalonePSF:
    def __init__(self, init_fwhm=2.5, n_star=20, peakmin=300, peakmax=3000,
                 max_ab_ratio=2.0, max_deviation=3.0, base_tile_size=500):
        self.init_fwhm = init_fwhm
        self.n_star = n_star
        self.peakmin = peakmin
        self.peakmax = peakmax         
        self.max_ab_ratio = max_ab_ratio 
        self.max_deviation = max_deviation
        self.base_tile_size = base_tile_size
        self.psf_cutout_size = int(5 * self.init_fwhm)
        self.fitter = fitting.LevMarLSQFitter()

    def _extract_psfs(self, ccd_cutout):
        data = ccd_cutout.data 
        if data.dtype.byteorder == '>':
                data = data.byteswap().view(data.dtype.newbyteorder())
        data = data.astype(np.float32)
        
        # 1. SEP Background Generation & Subtraction
        try:
            bkg = sep.Background(data)
            # We subtract the background directly from the data here!
            data_sub = data - bkg.back()
        except Exception:
            return [], [] 
            
        # 2. Extract sources from the background-subtracted data
        try:
            objects = sep.extract(data_sub, thresh=3.0, err=bkg.globalrms, minarea=np.pi*(0.5*self.init_fwhm)**2)
        except Exception:
            return [], []
            
        if objects is None or len(objects) == 0:
            return [], []
            
        ab_ratio = objects['a'] / objects['b']
        mask_valid = (
            (objects['peak'] > self.peakmin) & 
            (objects['peak'] < self.peakmax) &
            (ab_ratio <= self.max_ab_ratio)
        )
        objects = objects[mask_valid]
        
        if len(objects) == 0:
            return [], []
            
        objects = np.sort(objects, order='flux')[::-1][:self.n_star]
        
        center_pos = np.transpose((objects['x'], objects['y']))
        image_h, image_w = data.shape
        x_pos, y_pos = center_pos[:, 0], center_pos[:, 1]
        
        dist_to_border = np.minimum.reduce([
            x_pos, image_w - x_pos, 
            y_pos, image_h - y_pos
        ])
        
        mask_dist = dist_to_border >= (self.psf_cutout_size * 0.5)
        objects = objects[mask_dist]
        
        if len(objects) == 0:
            return [], []

        list_psf = []
        peak_values = []
        
        # 3. Extract Cutouts (Photutils annulus removed!)
        for x_center, y_center in zip(objects['x'], objects['y']):
            
            # CRITICAL: We extract from data_sub, which already has the background removed!
            cutout = Cutout2D(data_sub, position=(x_center, y_center), size=self.psf_cutout_size)
            psf_data = cutout.data.astype('float64')
            
            if psf_data.shape != (self.psf_cutout_size, self.psf_cutout_size) or np.isnan(psf_data).all():
                continue
                
            peak_val = np.nanmax(psf_data)
            
            # Normalize the PSF flux to 1.0 for the Gaussian fitter
            sum_flux = np.nansum(psf_data)
            if sum_flux > 0 and not np.isinf(sum_flux):
                psf_data /= sum_flux
            else:
                continue 
                
            peak_values.append(peak_val)
            list_psf.append(psf_data)
            
        return list_psf, peak_values

    def _fit_gaussians(self, psf_list):
        fwhms, thetas, flags = [], [], []
        
        for psf_data in psf_list:
            y, x = np.indices(psf_data.shape)
            y_center, x_center = psf_data.shape[0] / 2, psf_data.shape[1] / 2
            
            init_guess = Gaussian2D(
                amplitude=np.max(psf_data),
                x_mean=x_center, y_mean=y_center,
                x_stddev=self.init_fwhm/2.355, y_stddev=self.init_fwhm/2.355,
                theta=0
            )
            init_guess.x_stddev.bounds = (1e-5, None)
            init_guess.y_stddev.bounds = (1e-5, None)
            init_guess.amplitude.bounds = (0, None)
            
            model = self.fitter(init_guess, x, y, psf_data, filter_non_finite=True)
            
            if self.fitter.fit_info['ierr'] not in [1, 2, 3, 4]:
                flags.append(False)
                fwhms.append(np.nan)
                thetas.append(np.nan)
                continue
                
            x_stddev, y_stddev = model.x_stddev.value, model.y_stddev.value
            fwhm = 2 * np.sqrt(2 * np.log(2)) * np.sqrt(x_stddev * y_stddev)
            
            deviation = np.sqrt((model.x_mean.value - x_center)**2 + (model.y_mean.value - y_center)**2)
            flag = deviation <= self.max_deviation
            
            fwhms.append(fwhm)
            thetas.append(model.theta.value)
            flags.append(flag)
            
        return fwhms, thetas, flags

    def process_ccd(self, ccd_data):
        """
        Uses SOLORegion "Remainder Absorption" logic natively to ensure 
        100% of the sensor edges and corners are evaluated for focus.
        """
        h, w = ccd_data.shape
        result_table = []
        
        # Floor division calculates total full tiles
        num_tiles_x = w // self.base_tile_size
        num_tiles_y = h // self.base_tile_size
        
        for i in range(num_tiles_x):
            for j in range(num_tiles_y):
                
                # --- The SOLORegion Math ---
                x_start = i * self.base_tile_size
                y_start = j * self.base_tile_size
                
                # Extend the final tile to the absolute edge of the sensor
                x_end = w if i == num_tiles_x - 1 else (i + 1) * self.base_tile_size
                y_end = h if j == num_tiles_y - 1 else (j + 1) * self.base_tile_size
                
                size_x = x_end - x_start
                size_y = y_end - y_start
                
                x_center = x_start + (size_x / 2.0)
                y_center = y_start + (size_y / 2.0)
                # ---------------------------
                
                # Extract the cutout using the dynamically sized bounds
                ccd_cutout = Cutout2D(ccd_data, position=(x_center, y_center), size=(size_y, size_x))
                psf_list, peak_values = self._extract_psfs(ccd_cutout)
                
                if not psf_list:
                    continue  
                    
                fwhms, thetas, flags = self._fit_gaussians(psf_list)
                
                # Filter for valid star shapes
                valid_fwhms = [f for f, flag in zip(fwhms, flags) if flag and not np.isnan(f) and (1.5 < f < 10.0)]
                
                if not valid_fwhms:
                    continue
                
                result_table.append({
                    "fwhm_median": np.median(valid_fwhms)
                })
                
        return pd.DataFrame(result_table)


# ======================================================================
# MAIN V-CURVE EXECUTION SCRIPT
# ======================================================================

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
    
    # Initialize the standalone spatial PSF analyzer
    psf_analyzer = StandalonePSF(init_fwhm=2.5, n_star=20)
    
    obs_logger.info("Extracting FWHM data from focus images...")
    
    for fpath in fits_files:
        try:
            # We extract the focus position directly from the filename (e.g., focus_35000.fits)
            pos_str = str(fits.getheader(fpath).get("FOCUS", None))
            foc_pos = int(pos_str)
            
            # Read image directly as a numpy array using fits.getdata to avoid astropy CCDData overhead
            data = fits.getdata(fpath)
            
            # Process the 2D array
            df = psf_analyzer.process_ccd(data)
            
            if df.empty:
                obs_logger.warning(f"No valid stars found in {fpath.name}. Skipping.")
                continue
                
            # Get the median of the average FWHMs across all spatial regions
            overall_fwhm = df['fwhm_median'].mean()
            
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