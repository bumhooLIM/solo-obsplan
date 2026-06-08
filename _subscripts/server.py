import sys
import time
import argparse
import subprocess
import yaml
import socket
from pathlib import Path

# --- Connect to Root Directory ---
sys.path.append(str(Path(__file__).resolve().parent.parent))
import directory
from logger import obs_logger

# --- YAML Configuration Load ---
config_file = directory.INFO_DIR / "equipment.yaml"

with open(config_file, 'r') as file:
    config = yaml.safe_load(file)

ASCOM_SERVER_PATH = config['server']['path']
ASCOM_EXE_NAME = config['server']['exe']
SERVER_IP = config['server']['ip']
SERVER_PORT = config['server']['port']

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store", choices=['on', 'off'], required=True, help="Turn ASCOM server 'on' or 'off'")
args = parser.parse_args()

switch = args.switch.lower()

# --- Helper Function: Check Port ---
def is_port_open(ip, port):
    """Returns True if the network port is actively listening."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((ip, int(port)))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except:
        return False
    finally:
        s.close()

try:
    if switch == "on":
        obs_logger.info("Initializing ASCOM Remote Server boot sequence...")
        
        if is_port_open(SERVER_IP, SERVER_PORT):
            obs_logger.info("ASCOM Server is already running and listening on the port.")
        else:
            # Use Popen to open the server in the background
            subprocess.Popen(ASCOM_SERVER_PATH)
            obs_logger.info("Server GUI launched. Waiting for network initialization...")
            
            # --- The Safety Polling Loop ---
            timeout = 30
            start_time = time.time()
            server_ready = False
            
            while time.time() - start_time < timeout:
                if is_port_open(SERVER_IP, SERVER_PORT):
                    server_ready = True
                    break
                time.sleep(1) # Ping every 1 second
                
            if server_ready:
                # Add a tiny 2-second buffer just to let the internal Alpaca drivers settle
                time.sleep(2) 
                obs_logger.info("SUCCESS : ASCOM Remote Server is Online and Ready.")
            else:
                raise TimeoutError("ASCOM Server failed to open network port within 30 seconds.")
        
    elif switch == "off":
        obs_logger.info("Initiating ASCOM Remote Server termination...")
        
        # Use Windows taskkill to forcefully close the ASCOM server
        subprocess.run(["taskkill", "/F", "/IM", ASCOM_EXE_NAME], capture_output=True, check=True)
        obs_logger.info("SUCCESS : ASCOM Remote Server Terminated")

except subprocess.CalledProcessError:
    if switch == "off":
        obs_logger.warning("ASCOM Server might already be closed (Taskkill found no matching process).")
    else:
        obs_logger.error("FAIL : ASCOM Server Command Failed.")
         
except Exception as e:
    obs_logger.error(f"FAIL : ASCOM Server {switch.capitalize()} ({e})")