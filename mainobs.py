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
    
    try:
        
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
                if roof_proc.returncode != 0:
                    # The ONLY time we stop the entire sequence is if the roof is closed.
                    obs_logger.error("[FATAL ERROR] Roof is closed or network is down. Aborting entire night.")
                    break

            elif command == "start_sequence":
                obs_logger.info("--> Executing pre-observation startup sequence...")

                # 1. Turn on Mount Power
                subprocess.Popen([sys.executable, str(directory.SCRIPT_DIR / "power_switch.py"), "-s", "on"])
                sleep(10)
                
                # 2. Boot up the server.
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "server.py"), "-s", "on"])
                sleep(10)
                
                # 3. Check the parking status and park if necessary
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
                sleep(10)
                
                # 4. Home the mount
                home_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "homing.py"), "-c", "home"])
                if home_proc.returncode != 0:
                    obs_logger.warning("Homing failed. Proceeding with caution...")
                sleep(10)
                
                # 5. Cooler on
                temp = step.get('cooler_temp', -10.0) 
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "cooler.py"), "-s", "on", "-t", str(temp)])
                sleep(10)
                
            elif command == "end_sequence":
                obs_logger.info("--> Initiating after-observation shutdown sequence...")
                        
                # 1. Stop tracking and park the mount  
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
                sleep(10)
                
                # 2. Double check parking status and park if necessary
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
                sleep(10)
                
                # 3. Cooler off
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "cooler.py"), "-s", "off"])
                sleep(10) 
                
                # 4. Shutdown the server
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "server.py"), "-s", "off"])
                sleep(10)
                
                # 5. Turn off Mount Power
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "power_switch.py"), "-s", "off"])
                sleep(10)
                
            elif command == "park":
                obs_logger.info("--> Resetting telescope position to home...")
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
                sleep(10)
                
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
                sleep(10)
                
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
                    if current_alt <= 20.0 or (170.0 <= current_az <= 190.0):
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
                slew_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "goto_rd.py"), f"--ra={ra}", f"--dec={dec}"])
                
                # Check if goto_rd.py succeeded before exposing
                if slew_proc.returncode == 0:
                    sleep(60) # Give the mount a moment to settle after slewing before starting exposures
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
                
                elif slew_proc.returncode == 22:
                    obs_logger.error("[FATAL] Dawn detected by slew module. Skipping all remaining targets.")
                    skip_remaining_targets = True
                    continue
                    
                elif slew_proc.returncode == 23:
                    obs_logger.error(f"[FATAL] Global weather timeout reached during {name}. Skipping all remaining targets.")
                    skip_remaining_targets = True
                    continue
                    
                else:
                    obs_logger.warning(f"Slew failed for {name}. Instantly skipping to next target field...")
                    continue # Only skips this specific target if it was a standard mechanical error

            # elif command == "sync_field":
            #     name = step.get('target_name', 'Sync_Target')
            #     ra = str(step.get('ra'))
            #     dec = str(step.get('dec'))
            #     exptime = float(step.get('exptime', 10.0))

            #     obs_logger.info(f"--> [SYNC SEQUENCE] Calibrating mount coordinates for {name}...")

            #     # --- Step 1: Slew to Target ---
            #     slew_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "goto_rd.py"), f"--ra={ra}", f"--dec={dec}"])
            #     if slew_proc.returncode != 0:
            #         obs_logger.error(f"Slew failed for {name}. Aborting sync sequence.")
            #         continue
            #     sleep(60) 
                
            #     # --- Step 2: Take Reference Exposure ---
            #     obs_logger.info(f"Taking {exptime}-second reference exposure for plate solving...")
            #     exposure_proc = subprocess.run([
            #         sys.executable, str(directory.SCRIPT_DIR / "exposure.py"),
            #         "-n", "Sync_Image", 
            #         "-t", f"{exptime}", 
            #         "-i", "1",
            #         "-x", "1", 
            #         "-y", "1", 
            #         "--output_dir", str(daily_output_dir)
            #     ])
                
            #     if exposure_proc.returncode != 0:
            #         obs_logger.error("Failed to capture reference image. Aborting sync sequence.")
            #         continue
            #     sleep(10)
                
            #     # --- Step 3: Retrieve Image Path & Execute Query/Sync ---
            #     prev_img_file = directory.INFO_DIR / "prev_img.txt"
            #     if not prev_img_file.exists():
            #         obs_logger.error("FAIL: prev_img.txt not found. Cannot locate image for sync.")
            #         continue
                    
            #     with open(prev_img_file, "r") as f:
            #         target_fits_path = f.read().strip()
                
            #     # Execute the combined Query and Sync script!
            #     sync_proc = subprocess.run([
            #         sys.executable, str(directory.SCRIPT_DIR / "query_and_sync.py"), 
            #         "-f", target_fits_path
            #     ], capture_output=True, text=True)
                
            #     if sync_proc.returncode != 0:
            #         obs_logger.error("Query/Sync failed. Mount model was not updated.")
            #         # Print the exact Python crash log to your log_book.txt!
            #         obs_logger.error(f"CRASH DETAILS: {sync_proc.stderr.strip()}") 
            #         continue

            elif command == "focus_auto":
                obs_logger.info("--> [AUTOFOCUS SEQUENCE] Initiating V-Curve profiling...")
                
                f_start = int(step.get('range_start', 35500))
                f_end = int(step.get('range_end', 37500))
                raw_step = abs(int(step.get('step', 200)))
                # Auto-detect direction (Inward/Minus vs Outward/Plus)
                if f_start > f_end:
                    f_step = -raw_step
                else:
                    f_step = raw_step
                exptime = float(step.get('exptime', 5.0))
                
                # --- 0. Slew to Autofocus Target & Settle ---
                # Pull alt/az from the obsplan step. Defaults to Alt 70°, Az 270° (West) to avoid the meridian.
                focus_alt = float(step.get('alt', 45.0))
                focus_az = float(step.get('az', 270.0))
                
                obs_logger.info(f"Slewing to Autofocus field -> ALT: {focus_alt}° | AZ: {focus_az}°")
                slew_proc = subprocess.run([
                    sys.executable, str(directory.SCRIPT_DIR / "goto_aa.py"),
                    "-a", str(focus_alt), "-z", str(focus_az)
                ])
                
                if slew_proc.returncode != 0:
                    obs_logger.error("FAIL: Mount failed to reach autofocus field. Aborting autofocus sequence.")
                    continue

                # Turn on tracking
                track_proc = subprocess.run([
                    sys.executable, str(directory.SCRIPT_DIR / "tracking.py"),
                    "-t", "on"
                ])
                
                if track_proc.returncode != 0:
                    obs_logger.error("FAIL: tracking.py failed to engage tracking. Aborting autofocus sequence.")
                    continue
                    
                sleep(30.0) # wait for mount to settle and tracking to stabilize before starting the autofocus routine
                
                # --- 1. Prepare Temporary Focus Directory ---
                focus_dir = directory.DATA_DIR / "focus_temp"
                focus_dir.mkdir(parents=True, exist_ok=True)
                
                # Delete any old focus images from previous runs
                for f in focus_dir.glob("*.fits"):
                    f.unlink()
                    
                # --- 2. Record Initial Focus Position ---
                focus_proc = subprocess.run(
                    [sys.executable, str(directory.SCRIPT_DIR / "focus.py"), "-f", "0"],
                    capture_output=True, text=True
                )
                
                initial_focus = None
                # Search ONLY stdout for the clean, unformatted print string
                for line in focus_proc.stdout.split('\n'):
                    if line.startswith("FOCUS_POS:"):
                        initial_focus = int(line.split(":")[1].strip())
                
                if initial_focus is None:
                    obs_logger.error("FAIL: Could not read current focuser position. Aborting autofocus.")
                    continue
                    
                obs_logger.info(f"Initial focus position recorded as: {initial_focus}")
                current_focus = initial_focus
                
                # --- 3. The Imaging Loop ---
                positions = range(f_start, f_end + f_step, f_step)
                for pos in positions:
                    # Calculate relative steps to move
                    dx = pos - current_focus
                    obs_logger.info(f"Moving focuser to {pos}...")
                    move_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "focus.py"), "-f", str(dx)])
                    if move_proc.returncode != 0:
                        obs_logger.error(f"Focuser failed to move to {pos}. Aborting V-Curve.")
                        break 
                    current_focus = pos
                    
                    # Take Image (Named with focus position so find_best_focus.py can read it)
                    obs_logger.info(f"Taking {exptime}s exposure at focus {pos}...")
                    subprocess.run([
                        sys.executable, str(directory.SCRIPT_DIR / "exposure.py"),
                        "-n", f"focus_{pos}",
                        "-t", str(exptime),
                        "-i", "1",
                        "-x", "1", "-y", "1",
                        "--output_dir", str(focus_dir)
                    ])
                    
                # --- 4. Analyze Images & Fit V-Curve ---
                obs_logger.info("Analyzing images and fitting V-Curve...")
                analyze_proc = subprocess.run(
                    [sys.executable, str(directory.SCRIPT_DIR / "find_best_focus.py"), "-d", str(focus_dir)],
                    capture_output=True, text=True
                )
                
                best_focus = None
                for line in analyze_proc.stdout.split('\n'):
                    if line.startswith("BEST_FOCUS:"):
                        best_focus = int(line.split(":")[1].strip())
                        
                if best_focus is None:
                    obs_logger.error("FAIL: Could not calculate best focus from images.")
                    obs_logger.info(f"Reverting to initial focus position: {initial_focus}")
                    dx = initial_focus - current_focus
                    subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "focus.py"), "-f", str(dx)])
                    continue
                    
                # --- 5. The Safety Fallback Gate ---
                deviation = abs(best_focus - initial_focus)
                if deviation > 2000:
                    obs_logger.warning(f"DANGER: Best focus ({best_focus}) deviates from initial ({initial_focus}) by {deviation} steps!")
                    obs_logger.warning("This implies a bad V-Curve fit or heavy cloud cover. Ignoring result.")
                    obs_logger.info(f"Reverting to initial safe focus position: {initial_focus}")
                    target_focus = initial_focus
                else:
                    obs_logger.info(f"Best focus ({best_focus}) is within safe bounds (Deviation: {deviation}). Applying new focus.")
                    target_focus = best_focus
                    
                # --- 6. Final Focuser Adjustment ---
                dx = target_focus - current_focus
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "focus.py"), "-f", str(dx)])
                
                obs_logger.info(f"--> [AUTOFOCUS SEQUENCE] Complete. Final Position Locked: {target_focus}")
                
            elif command in ["dark", "bias"]: # Sets name to "Dark" or "Bias"
                # Bias overrides exptime to 0.01; Dark pulls it from the YAML
                
                exptime = float(step.get('exptime', 0.01)) if command == "dark" else 0.01
                name = str(command).lower() + f"{exptime:.0f}" if command == "dark" else "bias"
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

            # elif command == "confirm_end":
            #     obs_logger.info(f"\n[SYSTEM] Shutdown Complete. Successful Observations: {obs_completed}")
            #     break

            else:
                obs_logger.warning(f"Unknown command '{command}' in YAML. Skipping this step.")

    except Exception as e:
        obs_logger.error(f"[FATAL] Unhandled sequence exception: {e}")
    
    finally:
        obs_logger.info("--> [EMERGENCY/FINAL SHUTDOWN] Securing Observatory...")
        # 1. Stop Tracking
        subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
        sleep(10)
        
        # 2. Park Mount
        subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])
        sleep(10)
        
        # 3. Cooler Off
        subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "cooler.py"), "-s", "off"])
        sleep(10)
        
        # 4. Power Switch Off (Kills daemon)
        subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "power_switch.py"), "-s", "off"])
        sleep(10)

if __name__ == "__main__":
    execute_yaml_plan(directory.PLAN_DIR / "obsplan_example.yaml")