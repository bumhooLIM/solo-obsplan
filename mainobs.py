import os
import sys
import yaml
import subprocess
from datetime import datetime, timezone
from astropy import units as u
from time import sleep

# --- Direct Imports from Root ---
import directory
import util
from logger import obs_logger

# --- Load Observatory Configuration ---
obs_config_file = directory.INFO_DIR / "observatory.yaml"
try:
    with open(obs_config_file, 'r') as file:
        obs_config = yaml.safe_load(file)
        
    lat_str = str(obs_config['observatory']['latitude'])
    lon_str = str(obs_config['observatory']['longitude'])
    OBS_LAT = util.degree2float(lat_str) if hasattr(util, 'degree2float') else 37.07167
    OBS_LON = util.degree2float(lon_str) if hasattr(util, 'degree2float') else -119.41139
    OBS_ELEV = obs_config['observatory'].get('elevation', 1400)
    obs_name = obs_config['observatory'].get('name', 'Unknown Observatory')
    
    obs_logger.info(f"Loaded Observatory Info: {obs_name} (Lat: {OBS_LAT:.4f}°, Lon: {OBS_LON:.4f}°, Elev: {OBS_ELEV}m)")
except Exception as e:
    obs_logger.error(f"Failed to load observatory configuration: {e}")
    sys.exit(1)

# Data save paths
ut_now = datetime.now(timezone.utc)
date_str = ut_now.strftime('%Y_%m%d') # YYYY_MMDD format for daily folders
daily_output_dir = directory.DATA_DIR / date_str
daily_output_dir.mkdir(parents=True, exist_ok=True)

# --- Main Function to Execute YAML Plan ---
def execute_yaml_plan(yaml_file):
    
    if not os.path.exists(yaml_file):
        obs_logger.error(f"Plan file '{yaml_file}' not found.")
        return

    obs_logger.info(f"--- Starting SOLO Robotic Operation: {yaml_file} ---")
    
    with open(yaml_file, 'r') as file:
        try:
            plan = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            obs_logger.error(f"Failed to parse YAML file: {exc}")
            return

    obs_completed = 0 
    skip_remaining_targets = False

    for step_num, step in enumerate(plan, 1):
        command = step.get('command', '').lower()
        obs_logger.info(f">> [Step {step_num}] Executing: {command.upper()}")

        if command == "wait_until":
            target_ut = step.get('ut')
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "wait_until_ut.py"), "-u", target_ut])

        elif command == "check_observatory":
            obs_logger.info("--> Verifying observatory readiness...")
            roof_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "check_roof_status.py")])
            
            # The ONLY time we stop the entire sequence is if the roof is closed!
            if roof_proc.returncode != 0:
                obs_logger.error("[FATAL ERROR] Roof is closed or network is down. Aborting entire night.")
                break

        elif command == "start_sequence":
            obs_logger.info("--> Executing pre-observation startup sequence...")
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "server.py"), "-s", "on"])
            sleep(10) # Give the server a moment to boot up before we check the roof status
            # subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "unpark"])
            # subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "on"])
            temp = step.get('cooler_temp', -10.0) 
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "cooler.py"), "-s", "on", "-t", str(temp)])
            sleep(10)
            
        elif command == "end_sequence":
            obs_logger.info("--> Initiating after-observation shutdown sequence...")
            # subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
            # subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "cooler.py"), "-s", "off"])
            sleep(10) # Give the cooler a moment to power down before shutting off the server
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "server.py"), "-s", "off"])
            
        elif command == "observe_rd":
            name = step.get('target_name', 'unknown_target')
            
            # --- Global Skip Check ---
            if skip_remaining_targets:
                obs_logger.info(f"Skipping {name} due to prior weather/dawn abort.")
                continue
            
            ra = str(step.get('ra'))
            dec = str(step.get('dec'))
            exptime = float(step.get('exptime', 1.0))
            iterations = int(step.get('iter', 1))
            xbin = int(step.get('xbin', 1))
            ybin = int(step.get('ybin', 1))

            obs_logger.info(f"--> Checking observability for {name} (RA: {ra}, DEC: {dec})")
            
            # --- The "Instant Skip" Safety Block ---
            try:
                current_alt, current_az = util.equatorial2horizon(ra, dec, latitude=OBS_LAT*u.deg, longitude=OBS_LON*u.deg, height=OBS_ELEV*u.m, t="now")
                
                # If target is too low OR crossing the meridian
                if current_alt <= 15.0 or (170.0 <= current_az <= 190.0):
                    obs_logger.warning(f"Target {name} is unsafe! (Alt: {current_alt:.1f}°, Az: {current_az:.1f}°).")
                    obs_logger.info("Instantly skipping to the next target field...")
                    continue
                
                obs_logger.info(f"    [SYSTEM] Target safely observable (Alt: {current_alt:.1f}°, Az: {current_az:.1f}°). Proceeding.")
                
            except Exception as e:
                obs_logger.error(f"Observability check failed: {e}.")
                obs_logger.info("Instantly skipping to the next target field...")
                continue # Skip on calculation failure too

            # --- Execute if Safe ---
            obs_logger.info(f"--> Slewing to {name}")
            slew_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "goto_rd.py"), "-a", ra, "-d", dec])
            
            # Check if goto_rd.py succeeded before exposing
            if slew_proc.returncode == 0:
                sleep(30) # Give the mount a moment to settle after slewing before starting exposures
                obs_logger.info(f"--> Starting exposures for {name}")
                subprocess.run([
                    sys.executable, str(directory.SCRIPT_DIR / "exposure.py"),
                    "-n", name, 
                    "-t", f"{exptime:.2f}", 
                    "-i", str(iterations), 
                    "-x", str(xbin), 
                    "-y", str(ybin), 
                    "--output_dir", str(daily_output_dir)
                ])
                obs_completed += 1
            
            elif slew_proc.returncode == 2:
                obs_logger.error("[FATAL] Dawn detected by slew module. Skipping all remaining targets.")
                skip_remaining_targets = True
                continue
                
            elif slew_proc.returncode == 3:
                obs_logger.error(f"[FATAL] Global weather timeout reached during {name}. Skipping all remaining targets.")
                skip_remaining_targets = True
                continue
                
            else:
                obs_logger.warning(f"Slew failed for {name}. Instantly skipping to next target field...")
                continue # Only skips this specific target if it was a standard mechanical error

        elif command in ["dark", "bias"]:
            name = command.capitalize() # Sets name to "Dark" or "Bias"
            # Bias overrides exptime to 0.01; Dark pulls it from the YAML
            exptime = float(step.get('exptime', 0.01)) if command == "dark" else 0.01
            iterations = int(step.get('iter', 1))
            xbin = int(step.get('xbin', 1))
            ybin = int(step.get('ybin', 1))

            obs_logger.info(f"--> Starting calibration frames: {name} ({iterations}x {exptime}s)")
            
            # Call exposure.py with the correct --mode flag
            try:
                subprocess.run([
                    sys.executable, str(directory.SCRIPT_DIR / "exposure.py"),
                    "-n", name, 
                    "-t", f"{exptime:.2f}", 
                    "-i", str(iterations), 
                    "-x", str(xbin), 
                    "-y", str(ybin),
                    "-m", command, # Passes "dark" or "bias"
                    "--output_dir", str(daily_output_dir)
                ])
                obs_completed += iterations
            except Exception as e:
                obs_logger.error(f"Failed to execute calibration frames: {e}")

        elif command == "park":
            obs_logger.info("--> Resetting telescope position to home...")
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
            subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
            sleep(10) # Give the mount a moment to park before homing
            home_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "homing.py"), "-c", "home"])
            if home_proc.returncode != 0:
                obs_logger.warning("Homing failed. Proceeding with caution...")
            sleep(10)

        # elif command == "confirm_end":
        #     obs_logger.info(f"\n[SYSTEM] Shutdown Complete. Successful Observations: {obs_completed}")
        #     break

        else:
            obs_logger.warning(f"Unknown command '{command}' in YAML. Skipping this step.")

if __name__ == "__main__":
    execute_yaml_plan(directory.PLAN_DIR / "obsplan_example.yaml")