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
# Note the updated filename to match your new architecture
config_file = directory.INFO_DIR / "equipment.yaml"

with open(config_file, 'r') as file:
    config = yaml.safe_load(file)

camera_ip = config['camera']['ip']
camera_port = config['camera']['port']
C = Camera(camera_ip, camera_port)

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store", required=True)
parser.add_argument("-t", "--temp", dest="temp", type=float, default=-10.0)
args = parser.parse_args()

switch = args.switch.lower()

try:
    if switch == "on":
        obs_logger.info(f"Initializing FLI Cooler sequence (Target: {args.temp}°C)...")
        
        C.SetCCDTemperature = args.temp
        time.sleep(1.5) 
        C.CoolerOn = True
        
        obs_logger.info(f"Cooler On (Setpoint = {args.temp}°C)")
        
    elif switch == "off":
        C.CoolerOn = False
        obs_logger.info("Cooler Off")

except Exception as e:
    obs_logger.error(f"FAIL : Cooler {switch.capitalize()} ({e})")