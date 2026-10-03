import yaml
import numpy as np
from astropy.time import Time
import astropy.units as u
from astropy.coordinates import EarthLocation, get_sun, AltAz, SkyCoord
from pathlib import Path
import pandas as pd
from datetime import datetime

# --- 1. FIXED START AND CALIBRATION FUNCTIONS ---

def write_start_sequence(dusk_wait_ut):
    """Generates the startup and cooler initialization blocks."""
    return [
        {'command': 'wait_until', 'ut': dusk_wait_ut},
        {'command': 'check_observatory'},
        {'command': 'start_sequence', 'cooler_temp': -5.0}
    ]

def write_focus_auto(range_start, range_end, step, alt, az, exptime=5.0):
    """Generates the V-Curve autofocus block with specific Alt/Az pointing."""
    return [
        {
            'command': 'focus_auto', 
            'alt': alt,
            'az': az,
            'range_start': range_start, 
            'range_end': range_end, 
            'step': step, 
            'exptime': exptime
        }
    ]

def write_calibrations(dusk_targets, dawn_targets, num_darks=9, num_biases=9):
    """Dynamically finds unique exposure times and writes Dark and Bias commands."""
    blocks = []
    
    # 1. Bias Frames
    blocks.append({
        'command': 'bias',
        'iter': num_biases
    })
    
    # 2. Dark Frames
    all_targets = dusk_targets + dawn_targets
    unique_exposures = sorted(list(set([t['exptime'] for t in all_targets])))
    
    for ext in unique_exposures:
        blocks.append({
            'command': 'dark',
            'exptime': ext,
            'iter': num_darks
        })
    return blocks

# --- 2. OBSERVATION LOOP GENERATOR ---

def write_observe_loop(targets, num_loops):
    """Repeats a list of targets N times for the observation sequence."""
    blocks = []
    for _ in range(num_loops):
        for t in targets:
            block = {
                'command': 'observe_rd',
                'target_name': t['name'],
                'ra': t['ra'],
                'dec': t['dec'],
                'exptime': t['exptime'],
                'iter': t['iter']
            }
            blocks.append(block)
    return blocks

# --- 2b. TARGETED OBSERVATION (single pointing, altitude-limited) ---

def write_targeted_obs(date_str, location, t_start_str, target):
    """
    Generates an observe_target block for one night: a long sequence on a single pointing, from
    t_start until the target drops to target['alt_limit']. The pointing is the target's astrometric
    (RA, Dec) from JPL Horizons at the middle of that window, so the target stays centred on average.
    Returns (blocks, window_end_ut), or ([], None) if the target is not above the limit at t_start.
    """
    from astroquery.jplhorizons import Horizons # Only needed when targeted observations are configured

    t_start = Time(f"{date_str} {t_start_str}")
    eph = Horizons(
        id=target['horizons_id'], id_type='smallbody', location=target.get('site', 'U69'),
        epochs={'start': t_start.strftime("%Y-%m-%d %H:%M"), 'stop': (t_start + 12 * u.hour).strftime("%Y-%m-%d %H:%M"), 'step': '2m'}
    ).ephemerides(quantities='1,4')

    times = Time(np.asarray(eph['datetime_jd']), format='jd')
    above = np.asarray(eph['EL']) > target['alt_limit']
    if not above[0]:
        print(f"   ⚠️ {target['name']} is not above {target['alt_limit']} deg at {t_start_str} UT. No targeted observation tonight.")
        return [], None

    # The window ends when the target first drops to the altitude limit; point at its middle
    i_end = int(np.argmin(above)) if not above.all() else len(times) - 1
    i_mid = i_end // 2
    center = SkyCoord(eph['RA'][i_mid], eph['DEC'][i_mid], unit=u.deg)

    blocks = [{
        'command': 'observe_target',
        'target_name': target['name'],
        'ra': str(center.ra.to_string(unit=u.hourangle, sep=':', precision=2, pad=True)),
        'dec': str(center.dec.to_string(unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)),
        'exptime': target['exptime'],
        'iter': target['iter'],
        'alt_limit': target['alt_limit']
    }]
    return blocks, times[i_end].strftime("%H:%M:00")

# --- 3. DYNAMIC TIME & VISIBILITY CALCULATOR ---

# Pointing limits applied at run time by mainobs.py / goto_rd.py
OBS_ALT_MIN_DEG = 20.0             # Targets at or below this altitude are skipped
MERIDIAN_AZ_DEG = (170.0, 190.0)   # Azimuth band skipped to avoid meridian-flip trouble

def first_observable_time(targets, times, location, time_mask):
    """
    Returns the first time in times[time_mask] when ANY target is observable by mainobs.py's rules
    (Alt > 20 deg and Az outside the 170-190 deg meridian zone), or None if none ever is.
    """
    observable = np.zeros(len(times), dtype=bool)
    for t in targets:
        target = SkyCoord(t['ra'], t['dec'], unit=(u.hourangle, u.deg))
        target_altaz = target.transform_to(AltAz(obstime=times, location=location))

        in_meridian = (target_altaz.az.deg >= MERIDIAN_AZ_DEG[0]) & (target_altaz.az.deg <= MERIDIAN_AZ_DEG[1])
        observable |= (target_altaz.alt.deg > OBS_ALT_MIN_DEG) & ~in_meridian

    valid_mask = time_mask & observable
    return times[valid_mask][0] if np.any(valid_mask) else None

def calculate_wait_times(date_str, location, dusk_targets, dawn_targets):
    """
    Calculates the UT wait times of the night:
    - init:     Sun < -6 deg (start-up sequence)
    - dusk:     Sun < -12 deg (dusk autofocus)
    - dusk_obs: first time after dusk when ANY dusk target is observable, rounded up to the minute.
                Dusk fields often sit in the meridian zone right after dusk, where mainobs.py skips them.
                None if a dusk target is already observable at dusk (or none ever is).
    - dawn:     earliest time in the morning (Sun < -12 deg) when ANY dawn target is observable.
    """
    # Create an array of times for the next 24 hours at 12-second resolution
    t0 = Time(date_str + " 00:00:00") 
    times = t0 + np.linspace(0, 24, 7200) * u.hour
    
    sun_altaz = get_sun(times).transform_to(AltAz(obstime=times, location=location))
    
    # 1. initial wait time for entire sequence to start (Nautical Dusk)
    mask_init = sun_altaz.alt.deg < -6.0
    time_init = times[mask_init][0]  
    
    # 2. Dusk wait time for first target to be safely observable (Astronomical Dusk)
    mask_dusk = sun_altaz.alt.deg < -12.0
    time_dusk = times[mask_dusk][0]
    
    # 3. Dusk observing start: first time after dusk when ANY dusk target clears the pointing limits
    after_dusk_mask = (np.arange(len(times)) >= np.argmax(mask_dusk)) & mask_dusk
    time_dusk_obs = first_observable_time(dusk_targets, times, location, after_dusk_mask)
    if time_dusk_obs is not None and time_dusk_obs > time_dusk:
        dusk_obs_str = (time_dusk_obs + 1 * u.min).strftime("%H:%M:00") # Round up so the wait never ends early
    else:
        dusk_obs_str = None # Already observable at dusk (or never): no extra wait
    
    # 4. Earliest Dawn time when ANY target is observable in the morning (after solar midnight)
    solar_midnight_idx = np.argmin(sun_altaz.alt.deg)
    morning_mask = np.arange(len(times)) >= solar_midnight_idx
    morning_night_mask = morning_mask & (sun_altaz.alt.deg < -12.0)
    
    time_dawn = first_observable_time(dawn_targets, times, location, morning_night_mask)
    if time_dawn is None:
        time_dawn = times[morning_night_mask][-1]
    
    return time_init.strftime("%H:%M:00"), time_dusk.strftime("%H:%M:00"), dusk_obs_str, time_dawn.strftime("%H:%M:00")

# --- 4. MASTER COMPILER ---

def generate_daily_yaml(date_str, out_dir, dusk_targets, dawn_targets, location, dusk_loops=16, dawn_loops=16, targeted_obs=None):
    """Compiles all blocks together and exports the final obsplan.yaml"""
    
    time_init, time_dusk, time_dusk_obs, time_dawn = calculate_wait_times(date_str, location, dusk_targets, dawn_targets)
    
    # Targeted observations run back to back right after the dusk autofocus, each until its altitude limit
    targeted_blocks, targeted_end, targeted_info = [], time_dusk, []
    for target in (targeted_obs or []):
        blocks, t_end = write_targeted_obs(date_str, location, targeted_end, target)
        if blocks:
            targeted_info.append(f"{target['name']} {targeted_end[:5]}-{t_end[:5]} UT (until Alt {target['alt_limit']:.0f} deg) at RA {blocks[0]['ra']} Dec {blocks[0]['dec']}")
            targeted_blocks.extend(blocks)
            targeted_end = t_end
    
    plan = []
    
    # 1. Initialization & Dusk Prep
    plan.extend(write_start_sequence(time_init))
    plan.append({'command': 'wait_until', 'ut': time_dusk})
    if dusk_targets or targeted_blocks:
        plan.extend(write_focus_auto(range_start=19500, range_end=16500, step=500, alt=45.0, az=270.0, exptime=10.0))
    
    # 1b. Targeted Observations (after the dusk autofocus, before the dusk survey)
    plan.extend(targeted_blocks)
    
    # Dusk fields often transit right after dusk (inside the meridian zone that mainobs.py skips).
    # Park and wait until the first one clears instead of starting the loop too early
    # (not needed when targeted observations already run past that time).
    if dusk_targets and time_dusk_obs and targeted_end < time_dusk_obs:
        plan.append({'command': 'park'})
        plan.append({'command': 'wait_until', 'ut': time_dusk_obs})
    
    # 2. Dusk Target Loop
    plan.extend(write_observe_loop(dusk_targets, num_loops=dusk_loops))
    
    # 3. Dawn Wait & Safety Check
    plan.append({'command': 'park'})
    plan.append({'command': 'wait_until', 'ut': time_dawn})
    plan.append({'command': 'check_observatory'})
    
    # Re-focus before dawn loop
    if dawn_targets:
        plan.extend(write_focus_auto(range_start=19500, range_end=16500, step=500, alt=45.0, az=120.0, exptime=10.0))
    
    # 4. Dawn Target Loop
    plan.extend(write_observe_loop(dawn_targets, num_loops=dawn_loops))
    
    # --- 5. Shutdown & Calibrations (UPDATED ORDER) ---
    plan.append({'command': 'park'})  # 1. Park the mount first to stop tracking
    if dusk_targets or dawn_targets or targeted_blocks:
        plan.extend(write_calibrations(dusk_targets + targeted_blocks, dawn_targets, num_darks=9, num_biases=9)) # 2. Shoot calibrations (incl. darks for targeted exposure times)
    plan.append({'command': 'end_sequence'}) # 3. Warm up cooler & turn off servers
    plan.append({'command': 'compress_data'}) # 4. Compress all data generated tonight (High CPU task)
    
    # --- 6. Formatted File Export ---
    filename = out_dir / f"obsplan_{date_str.replace('-', '')}.yaml"
    
    raw_yaml = yaml.dump(plan, sort_keys=False, default_flow_style=False)
    formatted_yaml = raw_yaml.replace('\n- command:', '\n\n- command:')
    
    with open(filename, 'w') as file:
        file.write(formatted_yaml)
        
    print(f"✅ Successfully generated {filename}")
    print(f"   -> Observation start: {time_init}")
    print(f"   -> Dusk start: {time_dusk}")
    for info in targeted_info:
        print(f"   -> Targeted: {info}")
    if dusk_targets and time_dusk_obs and targeted_end < time_dusk_obs:
        print(f"   -> Dusk observing start: {time_dusk_obs} (after the meridian wait)")
    print(f"   -> Dawn start: {time_dawn}")

def generate_obs_dictionaries(fpath_csv):
    """
    Reads the tiled fields CSV and generates dictionary lists for the robotic obsplan.
    """
    # 1. Read the output CSV from the generator
    df = pd.read_csv(fpath_csv)

    # 2. Define the fields
    dusk_fields = []
    dawn_fields = []

    # 3. Separate the DataFrame into Dawn and Dusk sets based on the roi_label
    # Using .str.contains allows it to safely catch 'dawn', 'MorningROI', 'dusk', 'EveningROI', etc.
    df_dawn = df[df['label'].str.lower().str.contains('dawn|morning')]
    df_dusk = df[df['label'].str.lower().str.contains('evening')]

    # 4. Append Dusk Fields (starting the naming counter at 2)
    dusk_count = 1
    for _, row in df_dusk.iterrows():
        dusk_fields.append({
            'name': f'dusk_field{dusk_count}',
            'ra': str(row['ra_hms']),
            'dec': str(row['dec_dms']),
            'exptime': 60.0,
            'iter': 3
        })
        dusk_count += 1

    # 5. Append Dawn Fields (starting the naming counter at 2)
    dawn_count = 2
    for i, row in df_dawn.iterrows():
        dawn_fields.append({
            'name': f'dawn_field{dawn_count}',
            'ra': str(row['ra_hms']),
            'dec': str(row['dec_dms']),
            'exptime': 60.0,
            'iter': 3
        })
        dawn_count += 1

    return dusk_fields, dawn_fields

# ==========================================
# EXAMPLE USAGE
# ==========================================
if __name__ == "__main__":
    # Define your observatory location
    start_obsdate = "2026-10-02"
    end_obsdate = "2026-10-16"

    # Targeted observations: right after the dusk autofocus and before the dusk survey, until the pointing
    # drops to alt_limit (survey fields keep 20 deg). One pointing per night: the target's JPL Horizons
    # position at the middle of that window. Needs internet access on the listed nights.
    TARGETED_OBS = [
        {'name': '3200_Phaethon', 'horizons_id': '3200', 'first_night': '2026-10-02', 'last_night': '2026-10-04',
         'exptime': 10.0, 'iter': 1000, 'alt_limit': 15.0},
        {'name': '3200_Phaethon', 'horizons_id': '3200', 'first_night': '2026-10-05', 'last_night': '2026-10-06',
         'exptime': 10.0, 'iter': 1000, 'alt_limit': 20.0},
    ]

    for obsdate in pd.date_range(start=start_obsdate, end=end_obsdate):
        obsdate = obsdate.strftime("%Y-%m-%d")
        refdate = "2026-10-08" # reference folder for the obsfields results

        yyyymmdd = datetime.strptime(obsdate, "%Y-%m-%d").strftime("%Y%m%d")
        yyyy_mm = datetime.strptime(obsdate, "%Y-%m-%d").strftime("%Y_%m")
        
        SRO_LOC = EarthLocation(lat=37.04 * u.deg, lon=-119.41 * u.deg, height=1400 * u.m)
        OBSPLAN_DIR = Path(f"./obsplans/{yyyy_mm}")
        OBSPLAN_DIR.mkdir(parents=True, exist_ok=True)
        OBSFIELD_DIR = Path(f"./obsfields/results/{refdate.replace('-', '')}/fields")
        # OBSPLAN_DIR.mkdir(exist_ok=True)
        
        # Bring in the target fields from the CSV generated by obsfields_generator.ipynb
        # dusk_fields, dawn_fields = generate_obs_dictionaries(csv_file)
        # Define Evening Targets (Dusk)
        dusk_fields, dawn_fields = generate_obs_dictionaries(OBSFIELD_DIR / f"fields_{yyyymmdd}.csv")
        
        generate_daily_yaml(
            date_str=obsdate,
            out_dir=OBSPLAN_DIR,
            dusk_targets=dusk_fields,
            dawn_targets=dawn_fields,
            location=SRO_LOC,
            dusk_loops=30, 
            dawn_loops=30,
            targeted_obs=[t for t in TARGETED_OBS if t['first_night'] <= obsdate <= t['last_night']]
        )