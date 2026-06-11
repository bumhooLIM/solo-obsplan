import sys
import argparse
import bz2
from pathlib import Path
from tqdm import tqdm

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dir", dest="dir", required=True, help="Target directory containing .fits files")
args = parser.parse_args()

def compress_files():
    target_dir = Path(args.dir)
    
    if not target_dir.exists() or not target_dir.is_dir():
        obs_logger.error(f"FAIL: Compression directory does not exist -> {target_dir}")
        sys.exit(1)

    list_fpath_fits = list(target_dir.glob("*.fits"))
    num_files = len(list_fpath_fits)
    
    if num_files == 0:
        obs_logger.info(f"No .fits files found to compress in {target_dir}")
        sys.exit(0)

    obs_logger.info(f"Starting bz2 compression for {num_files} .fits files...")

    success_count = 0
    try:
        # We keep tqdm for the terminal output, but log the start/end to keep the log file clean
        for fpath_fits in tqdm(list_fpath_fits, total=num_files, desc="Compressing to .bz2"):
            fpath_fits_bz2 = fpath_fits.with_suffix(".fits.bz2")
            
            with open(fpath_fits, "rb") as f_in, bz2.open(fpath_fits_bz2, "wb") as f_out:
                f_out.write(f_in.read())
            
            # Delete original file to save space
            fpath_fits.unlink()
            success_count += 1
            
        obs_logger.info(f"SUCCESS: Compressed {success_count}/{num_files} files in {target_dir}")
        sys.exit(0)
        
    except Exception as e:
        obs_logger.error(f"FAIL: Error occurred during bz2 compression ({e})")
        sys.exit(1)

if __name__ == "__main__":
    compress_files()