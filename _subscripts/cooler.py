import sys
import time
import argparse
import yaml
from pathlib import Path
from alpaca.camera import Camera

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
try:
    with open(directory.INFO_DIR / "equipment.yaml", 'r') as file:
        eq = yaml.safe_load(file)
        
    camera_addr = f"{eq['camera']['ip']}:{eq['camera']['port']}"
    camera_device = eq['camera']['device_number']
    C = Camera(camera_addr, camera_device)
except Exception as e:
    obs_logger.error(f"FAIL: Could not load configuration or connect to camera ({e})")
    sys.exit(1)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store", required=True)
parser.add_argument("-t", "--temp", dest="temp", type=float, default=-10.0)
args = parser.parse_args()

switch = args.switch.lower()

try:
    if switch == "on":
        obs_logger.info(f"Initializing FLI Cooler sequence (Target: {args.temp}°C)...")
        
        # 1. Turn on the cooler
        C.CoolerOn = True
        time.sleep(3.0) 
        C.SetCCDTemperature = args.temp
        
        obs_logger.info(f"Cooler On. Waiting for temperature to stabilize near {args.temp}°C...")
        
        # --- 2. The Temperature Polling Loop ---
        timeout = 1800 # 30 minutes maximum wait
        tolerance = 1.0 # Within 1 degree is considered "SUCCESS"
        start_time = time.time()
        
        heartbeat_interval = 60 # Log the current temp every 60 seconds
        last_heartbeat = time.time()
        
        while True:
            current_temp = C.CCDTemperature
            
            # Condition A: We reached the target temperature
            if abs(current_temp - args.temp) <= tolerance:
                obs_logger.info(f"SUCCESS : Camera temperature stabilized at {current_temp:.1f}°C.")
                break
                
            # Condition B: Timeout (Protect against hot summer nights where the target is impossible)
            if time.time() - start_time > timeout:
                cooler_pwr = getattr(C, 'CoolerPower', 'Unknown')
                obs_logger.warning(f"TIMEOUT : Cooler reached {current_temp:.1f}°C but could not reach {args.temp}°C within {timeout/60:.1f} mins.")
                obs_logger.warning(f"Cooler Power is at {cooler_pwr}%. Proceeding with observation anyway.")
                break
                
            # Condition C: Heartbeat Logging
            if time.time() - last_heartbeat > heartbeat_interval:
                cooler_pwr = getattr(C, 'CoolerPower', 'Unknown')
                obs_logger.info(f"Status: Cooling in progress... (Current: {current_temp:.1f}°C / Target: {args.temp}°C / Power: {cooler_pwr}%)")
                last_heartbeat = time.time()
                
            time.sleep(30) # Check temperature every 30 seconds
        
    elif switch == "off":
        obs_logger.info("Initiating camera warm-up sequence...")
        C.CoolerOn = False
        obs_logger.info("Cooler Off")

except Exception as e:
    obs_logger.error(f"FAIL : Cooler {switch.capitalize()} ({e})")
    sys.exit(1)