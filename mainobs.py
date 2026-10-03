import os
import sys
import yaml
import subprocess
import argparse
from datetime import datetime, timezone
from astropy import units as u
from astropy.time import Time
from astropy.coordinates import EarthLocation, AltAz, get_sun
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

# --- Pointing Limits (same values as _subscripts/goto_rd.py) ---
ALT_LIMIT_DEG = 20.0               # Targets at or below this altitude are skipped
MERIDIAN_AZ_DEG = (170.0, 190.0)   # Azimuth band skipped to avoid meridian-flip trouble
DAWN_SUN_ALT_DEG = -10.0           # Sun above this altitude = dawn (goto_rd.py exit code 22)
TARGET_ALT_LIMIT_DEG = 15.0        # Default altitude limit for observe_target (targeted observations only)

# --- Meridian Wait Settings (see observe_rd) ---
MERIDIAN_WAIT_MAX_MIN = 120        # Give up waiting for a field to clear the meridian after this
MERIDIAN_WAIT_POLL_SEC = 60        # Re-check interval while waiting
MERIDIAN_WAIT_HEARTBEAT_MIN = 10   # Status log interval while waiting

# --- Roof Re-check Settings (see check_observatory) ---
ROOF_RECHECK_MIN = 60              # Re-check a closed roof this often, until morning twilight

def pointing_status(ra, dec, alt_limit=ALT_LIMIT_DEG):
    """Returns ('ok' | 'low' | 'meridian', alt, az) for a target at the current time."""
    alt, az = util.equatorial2horizon(ra, dec, latitude=OBS_LAT*u.deg, longitude=OBS_LON*u.deg, height=OBS_ELEV*u.m, t="now")
    if alt <= alt_limit:
        return "low", alt, az
    if MERIDIAN_AZ_DEG[0] <= az <= MERIDIAN_AZ_DEG[1]:
        return "meridian", alt, az
    return "ok", alt, az

def sun_altitude_now(dt_min=0):
    """Returns the altitude of the Sun in degrees, now or dt_min minutes from now."""
    loc = EarthLocation(lat=OBS_LAT*u.deg, lon=OBS_LON*u.deg, height=OBS_ELEV*u.m)
    t = Time.now() + dt_min * u.min
    return get_sun(t).transform_to(AltAz(obstime=t, location=loc)).alt.deg

def is_morning_twilight():
    """True once the Sun is rising and above DAWN_SUN_ALT_DEG, i.e. the night is over."""
    alt_now = sun_altitude_now()
    return alt_now > DAWN_SUN_ALT_DEG and sun_altitude_now(dt_min=10) > alt_now

def roof_is_open():
    """Runs check_roof_status.py. True if the roof reports OPEN."""
    return subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "check_roof_status.py")]).returncode == 0

def wait_for_roof_open():
    """
    Returns True as soon as the roof reports OPEN. While it is closed (or the status file is unreadable),
    re-checks every ROOF_RECHECK_MIN minutes, and returns False once morning twilight has started.
    """
    while not roof_is_open():
        if is_morning_twilight():
            return False
        obs_logger.warning(f"Roof is CLOSED or its status is unreadable. Re-checking in {ROOF_RECHECK_MIN} min (until morning twilight)...")
        sleep(ROOF_RECHECK_MIN * 60)
    return True

def observe_block(plan, start_idx):
    """
    Returns the unique fields [(name, ra, dec), ...] of the run of consecutive observe_rd steps
    starting at plan[start_idx], and the plan index right after that run.
    """
    fields = {}
    end_idx = start_idx
    while end_idx < len(plan) and str(plan[end_idx].get('command', '')).lower() == "observe_rd":
        block_step = plan[end_idx]
        fields.setdefault((str(block_step.get('ra')), str(block_step.get('dec'))), block_step.get('target_name', 'unknown_target'))
        end_idx += 1
    return [(name, ra, dec) for (ra, dec), name in fields.items()], end_idx

def wait_for_meridian_clear(fields):
    """
    Parks the mount and waits until any field of the block becomes observable.
    Returns 'ready', 'set' (every field dropped below the altitude limit), 'dawn' or 'timeout'.
    """
    obs_logger.info(f"--> [MERIDIAN WAIT] No field in this block is observable, but some are only blocked by the meridian zone (Az {MERIDIAN_AZ_DEG[0]:.0f}-{MERIDIAN_AZ_DEG[1]:.0f}°). Parking and waiting (max {MERIDIAN_WAIT_MAX_MIN} min)...")

    # Secure the mount while waiting (goto_rd.py unparks it before the next slew)
    subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "tracking.py"), "-t", "off"])
    subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "parking.py"), "-p", "park"])

    t_start = Time.now()
    t_heartbeat = t_start

    while True:
        statuses = [(name, *pointing_status(ra, dec)) for name, ra, dec in fields]
        waited_min = (Time.now() - t_start).to(u.min).value

        for name, status, alt, az in statuses:
            if status == "ok":
                obs_logger.info(f"--> [MERIDIAN WAIT] {name} is now observable (Alt: {alt:.1f}°, Az: {az:.1f}°) after {waited_min:.0f} min. Resuming.")
                return "ready"

        if not any(status == "meridian" for _, status, _, _ in statuses):
            obs_logger.warning("[MERIDIAN WAIT] Every field dropped below the altitude limit while waiting. Ending this block.")
            return "set"

        if sun_altitude_now() > DAWN_SUN_ALT_DEG:
            obs_logger.error("[MERIDIAN WAIT] Dawn detected while waiting. Skipping all remaining targets.")
            return "dawn"

        if waited_min >= MERIDIAN_WAIT_MAX_MIN:
            obs_logger.warning(f"[MERIDIAN WAIT] TIMEOUT after {waited_min:.0f} min. Falling back to skipping this block's fields.")
            return "timeout"

        if (Time.now() - t_heartbeat).to(u.min).value >= MERIDIAN_WAIT_HEARTBEAT_MIN:
            positions = ", ".join(f"{name} Az {az:.1f}°" for name, _, _, az in statuses)
            obs_logger.info(f"Status: Still waiting for the meridian to clear ({waited_min:.0f} min elapsed; {positions}).")
            t_heartbeat = Time.now()

        sleep(MERIDIAN_WAIT_POLL_SEC)

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
        meridian_wait_off_until = 0 # Plan index before which the meridian wait is disabled (after a timeout)
        startup_done = False # True once start_sequence has powered up the hardware (see check_observatory)

        for step_num, step in enumerate(plan, 1):
            
            command = step.get('command', '').lower()
            obs_logger.info(f">> [Step {step_num}] Executing: {command.upper()}")

            if command == "wait_until":
                target_ut = step.get('ut')
                subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "wait_until_ut.py"), "-u", target_ut])

            elif command == "check_observatory":
                obs_logger.info("--> Verifying observatory readiness...")
                
                # A closed roof no longer ends the night at once: re-check every ROOF_RECHECK_MIN until it opens.
                # The night is aborted only if it is still closed when morning twilight starts.
                if not wait_for_roof_open():
                    obs_logger.error("[FATAL ERROR] Roof stayed closed (or network is down) until morning twilight. Aborting entire night.")
                    break

                # Before start-up, a roof that only opened after morning twilight began is too late to start the night
                if not startup_done and is_morning_twilight():
                    obs_logger.error("[FATAL ERROR] Roof opened only after morning twilight began. Too late to start the night. Aborting.")
                    break

            elif command == "start_sequence":
                obs_logger.info("--> Executing pre-observation startup sequence...")
                startup_done = True

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
                    status, current_alt, current_az = pointing_status(ra, dec)
                    
                    # --- Meridian Wait ---
                    # Skips are instant and the loop is a fixed list of steps, so if no field of this block is
                    # observable the whole loop drains in minutes. Dusk fields typically sit in the meridian zone
                    # right after dusk: if that is the only obstacle, wait for the first field to clear it.
                    if status != "ok" and (step_num - 1) >= meridian_wait_off_until:
                        block_fields, block_end = observe_block(plan, step_num - 1)
                        block_status = [pointing_status(f_ra, f_dec)[0] for _, f_ra, f_dec in block_fields]
                        
                        if "ok" not in block_status and "meridian" in block_status:
                            wait_result = wait_for_meridian_clear(block_fields)
                            
                            if wait_result == "dawn":
                                skip_remaining_targets = True
                                continue
                            if wait_result == "timeout":
                                meridian_wait_off_until = block_end # Don't wait again within this block
                            
                            status, current_alt, current_az = pointing_status(ra, dec)
                    
                    # If target is too low OR crossing the meridian
                    if status != "ok":
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

            elif command == "observe_target":
                # --- Targeted Observation: one long sequence on a fixed pointing (e.g. a specific asteroid) ---
                # Uses its own altitude limit (alt_limit, default 15 deg) instead of the survey's 20 deg.
                # exposure.py stops the frames once the pointing drops to alt_limit or the roof closes,
                # so 'iter' is only an upper bound.
                name = step.get('target_name', 'unknown_target')

                if skip_remaining_targets:
                    obs_logger.info(f"Skipping {name} due to prior weather/dawn abort.")
                    continue

                ra = str(step.get('ra'))
                dec = str(step.get('dec'))
                exptime = float(step.get('exptime', 10.0))
                iterations = int(step.get('iter', 1))
                xbin = int(step.get('xbin', 1))
                ybin = int(step.get('ybin', 1))
                alt_limit = float(step.get('alt_limit', TARGET_ALT_LIMIT_DEG))

                obs_logger.info(f"--> [TARGETED] Checking observability for {name} (RA: {ra}, DEC: {dec}, Alt limit: {alt_limit:.0f}°)")

                try:
                    status, current_alt, current_az = pointing_status(ra, dec, alt_limit=alt_limit)
                    if status != "ok":
                        obs_logger.warning(f"Target {name} is unsafe! (Alt: {current_alt:.1f}°, Az: {current_az:.1f}°). Skipping targeted observation.")
                        continue
                except Exception as e:
                    obs_logger.error(f"Observability check failed: {e}. Skipping targeted observation.")
                    continue

                obs_logger.info(f"--> Slewing to {name}")
                slew_proc = subprocess.run([sys.executable, str(directory.SCRIPT_DIR / "goto_rd.py"), f"--ra={ra}", f"--dec={dec}", f"--min_alt={alt_limit}"])

                if slew_proc.returncode == 0:
                    sleep(60) # Give the mount a moment to settle after slewing before starting exposures
                    obs_logger.info(f"--> Starting targeted exposures for {name} (up to {iterations}x {exptime}s, until Alt <= {alt_limit:.0f}°)")
                    subprocess.run([
                        sys.executable, str(directory.SCRIPT_DIR / "exposure.py"),
                        "-n", name,
                        "-t", f"{exptime:.2f}",
                        "-i", str(iterations),
                        "-x", str(xbin),
                        "-y", str(ybin),
                        "--output_dir", str(daily_output_dir),
                        f"--min_alt={alt_limit}", f"--ra={ra}", f"--dec={dec}"
                    ])
                    obs_completed += 1

                elif slew_proc.returncode == 22:
                    obs_logger.error("[FATAL] Dawn detected by slew module. Skipping all remaining targets.")
                    skip_remaining_targets = True

                elif slew_proc.returncode == 23:
                    obs_logger.error(f"[FATAL] Global weather timeout reached during {name}. Skipping all remaining targets.")
                    skip_remaining_targets = True

                else:
                    obs_logger.warning(f"Slew failed for {name}. Skipping targeted observation.")

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

            elif command == "compress_data":
                obs_logger.info(f"--> [DATA COMPRESSION] Compressing FITS files in {daily_output_dir}...")
                
                compress_proc = subprocess.run([
                    sys.executable, str(directory.SCRIPT_DIR / "compress_bz2.py"),
                    "-d", str(daily_output_dir)
                ])
                
                if compress_proc.returncode != 0:
                    obs_logger.warning("Data compression encountered an error. Check logs for details.")
                else:
                    obs_logger.info("--> [DATA COMPRESSION] Complete.")
                    
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
    parser = argparse.ArgumentParser(description="SOLO Robotic Observation Main Script")
    parser.add_argument("-f", "--file", dest="plan_file", required=True, help="Name of the YAML plan file (e.g., obsplan_20260612.yaml)")
    args = parser.parse_args()

    # Automatically look for the file inside the PLAN_DIR
    plan_path = directory.PLAN_DIR / args.plan_file

    execute_yaml_plan(plan_path)