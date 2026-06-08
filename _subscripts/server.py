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
MOUNT_EXE_NAME = config['server'].get('mount_exe', None)
SERVER_IP = config['server']['ip']
SERVER_PORT = config['server']['port']

# --- Argparse Setting ---
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store", choices=['on', 'off'], required=True, help="Turn ASCOM server 'on' or 'off'")
args = parser.parse_args()

switch = args.switch.lower()

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
            subprocess.Popen(ASCOM_SERVER_PATH)
            obs_logger.info("Server GUI launched. Waiting for network initialization...")
            
            timeout = 30
            start_time = time.time()
            server_ready = False
            
            while time.time() - start_time < timeout:
                if is_port_open(SERVER_IP, SERVER_PORT):
                    server_ready = True
                    break
                time.sleep(1)
                
            if server_ready:
                time.sleep(2) 
                obs_logger.info("SUCCESS : ASCOM Remote Server is Online and Ready.")
            else:
                raise TimeoutError("ASCOM Server failed to open network port within 30 seconds.")
        
    elif switch == "off":
        obs_logger.info("Initiating graceful shutdown of ASCOM drivers and server...")
        
        # --- 1. Graceful Soft Disconnect ---
        # Tells the driver to securely close COM ports before we kill the UI
        try:
            from alpaca.telescope import Telescope
            from alpaca.camera import Camera
            
            addr = f"{SERVER_IP}:{SERVER_PORT}"
            
            # Disconnect Mount
            T = Telescope(addr, config['telescope']['device_number'])
            if getattr(T, 'Connected', False):
                T.Connected = False
                obs_logger.info("Telescope driver cleanly disconnected.")
                
            # Disconnect Camera
            C = Camera(addr, config['camera']['device_number'])
            if getattr(C, 'Connected', False):
                C.Connected = False
                obs_logger.info("Camera driver cleanly disconnected.")
        except Exception:
            pass # Ignore if the server is already dead or unreachable
            
        time.sleep(2) # Give the COM ports 2 seconds to release their hardware locks

        # --- 2. Hard Kill the Processes ---
        # Kill ASCOM Remote Server
        subprocess.run(["taskkill", "/F", "/IM", ASCOM_EXE_NAME], capture_output=True)
        
        # Kill the specific Mount Driver (HUBOI)
        if MOUNT_EXE_NAME:
            subprocess.run(["taskkill", "/F", "/IM", MOUNT_EXE_NAME], capture_output=True)
            
        obs_logger.info("SUCCESS : ASCOM Remote Server and Background Drivers Terminated")

except subprocess.CalledProcessError:
    if switch == "off":
        obs_logger.warning("ASCOM Servers might already be closed (Taskkill found no matching process).")
    else:
        obs_logger.error("FAIL : ASCOM Server Command Failed.")
         
except Exception as e:
    obs_logger.error(f"FAIL : ASCOM Server {switch.capitalize()} ({e})")