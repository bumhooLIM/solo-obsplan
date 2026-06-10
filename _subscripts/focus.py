import sys
import time
import argparse
import yaml
from pathlib import Path
from alpaca.focuser import Focuser

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq_config = yaml.safe_load(file)
    
    # Apply the Alpaca networking fix
    focuser_address = f"{eq_config['focuser']['ip']}:{eq_config['focuser']['port']}"
    focuser_device = eq_config['focuser']['device_number']
    F = Focuser(focuser_address, focuser_device)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to focuser ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-f", "--dx", dest="dx", type=int, default=0, help="Relative steps to move focus (e.g., 50 or -50). Use 0 just to check status.")
args = parser.parse_args()

def execute_focus():
    try:
        dx = args.dx
        current_pos = getattr(F, 'Position', 0)

        # If dx is 0, we just log the current position and exit
        if dx == 0:
            obs_logger.info(f"Current Focuser Position: {current_pos}")
            # Add this raw print so mainobs.py can safely capture it:
            print(f"FOCUS_POS:{current_pos}") 
            sys.exit(0)

        # --- 1. Calculate Target & Enforce Boundaries ---
        # The ZWO EAF is an "Absolute" focuser, meaning F.Move() requires an absolute coordinate, not a relative step.
        target_pos = current_pos + dx
        
        max_step = getattr(F, 'MaxStep', 60000) # Default to 60k if not specified by driver
        
        if target_pos < 0:
            obs_logger.warning(f"Target position ({target_pos}) is below 0. Capping at 0.")
            target_pos = 0
        elif target_pos > max_step:
            obs_logger.warning(f"Target position ({target_pos}) exceeds MaxStep ({max_step}). Capping at {max_step}.")
            target_pos = max_step

        obs_logger.info(f"Moving focuser by {dx} steps (From {current_pos} -> {target_pos})...")

        # --- 2. Execute Movement ---
        F.Move(target_pos)
        
        # Buffer to let the ASCOM driver register the moving state
        time.sleep(0.5)

        # --- 3. Dynamic Wait Loop ---
        timeout = 60 # Maximum wait time of 60 seconds for very large moves
        start_time = time.time()
        
        while getattr(F, 'IsMoving', False):
            if time.time() - start_time > timeout:
                obs_logger.error(f"TIMEOUT: Focuser failed to reach target within {timeout} seconds.")
                try:
                    F.Halt() # Send emergency stop to focuser
                    obs_logger.warning("Emergency Halt command sent to focuser.")
                except:
                    pass
                sys.exit(1)
            time.sleep(0.2) # Check status rapidly (every 0.2s)
            
        # --- 4. Verification ---
        final_pos = getattr(F, 'Position', 0)
        obs_logger.info(f"SUCCESS : Focuser movement complete. New position: {final_pos}")

    except Exception as e:
        obs_logger.error(f"FAIL : Focuser Error ({e})")
        sys.exit(1)

if __name__ == "__main__":
    execute_focus()