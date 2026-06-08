import sys
from pathlib import Path
import yaml

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
config_file = directory.INFO_DIR / "observatory.yaml"

try:
    with open(config_file, 'r') as file:
        config = yaml.safe_load(file)
    
    roof_file_path = config['observatory'].get('roof_status_file', r"D:\RoofStatusFile.txt")
    ROOF_STATUS_FILE = Path(roof_file_path)
except Exception as e:
    obs_logger.error(f"FAIL : Could not load observatory configuration ({e})")
    sys.exit(1)

def verify_roof():
    obs_logger.info(f"Checking local roof status via networked drive...")

    # 1. Check if the network drive dropped or the file is missing
    if not ROOF_STATUS_FILE.exists():
        obs_logger.error(f"FAIL : Roof status file not found at {ROOF_STATUS_FILE}. Aborting for safety.")
        sys.exit(1)

    try:
        # 2. Read the file (errors='ignore' prevents crashes from the '???' garbage bytes)
        with open(ROOF_STATUS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline().strip().upper()

        # 3. Fuzzy match the status
        if "OPEN" in first_line:
            # Clean up the output string to look nice in your log file
            clean_status = first_line.replace('???', '').strip()
            obs_logger.info(f"SUCCESS : Observatory Roof is confirmed OPEN. ({clean_status})")
            sys.exit(0) # 0 means "All Good" to the master script
            
        elif "CLOSE" in first_line:
            clean_status = first_line.replace('???', '').strip()
            obs_logger.error(f"FAIL : Observatory Roof is CLOSED. ({clean_status})")
            sys.exit(1) # 1 means "Error" to the master script
            
        else:
            obs_logger.error(f"FAIL : Unrecognized status in roof file: '{first_line}'")
            sys.exit(1)

    except Exception as e:
        obs_logger.error(f"FAIL : Could not read the roof status file ({e})")
        sys.exit(1)

if __name__ == "__main__":
    verify_roof()