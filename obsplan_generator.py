import yaml
import numpy as np
from astropy.time import Time
import astropy.units as u
from astropy.coordinates import EarthLocation, get_sun, AltAz, SkyCoord
from pathlib import Path

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

# --- 3. DYNAMIC TIME & VISIBILITY CALCULATOR ---

def calculate_wait_times(date_str, location, dawn_targets):
    """
    Calculates the exact UT time for Dusk (Sun < -10 deg) and Dawn.
    Dawn wait considers ALL dawn targets and fits to the earliest 
    time ANY of them crosses 20 deg in the morning.
    """
    # Create an array of times for the next 24 hours at 12-second resolution
    t0 = Time(date_str + " 00:00:00") 
    times = t0 + np.linspace(0, 24, 7200) * u.hour
    
    sun_altaz = get_sun(times).transform_to(AltAz(obstime=times, location=location))
    
    # 1. DUSK WAIT: When Sun drops below -10 degrees (Nautical)
    dusk_mask_nat = sun_altaz.alt.deg < -5.0
    dusk_time_nat = times[dusk_mask_nat][0]  
    
    dusk_mask_ast = sun_altaz.alt.deg < -10.0
    dusk_time_ast = times[dusk_mask_ast][0]
    
    # 2. DAWN WAIT: Find earliest rising target in the morning
    solar_midnight_idx = np.argmin(sun_altaz.alt.deg)
    morning_mask = np.arange(len(times)) >= solar_midnight_idx
    
    dawn_start_times = []
    
    for t in dawn_targets:
        target = SkyCoord(t['ra'], t['dec'], unit=(u.hourangle, u.deg))
        target_altaz = target.transform_to(AltAz(obstime=times, location=location))
        
        valid_mask = morning_mask & (sun_altaz.alt.deg < -10.0) & (target_altaz.alt.deg > 20.0)
        
        if np.any(valid_mask):
            dawn_start_times.append(times[valid_mask][0])
            
    if dawn_start_times:
        dawn_time = min(dawn_start_times)
    else:
        morning_night_mask = morning_mask & (sun_altaz.alt.deg < -10.0)
        dawn_time = times[morning_night_mask][-1]
    
    return dusk_time_nat.strftime("%H:%M:00"), dusk_time_ast.strftime("%H:%M:00"), dawn_time.strftime("%H:%M:00")

# --- 4. MASTER COMPILER ---

def generate_daily_yaml(date_str, dusk_targets, dawn_targets, location, dusk_loops=16, dawn_loops=16):
    """Compiles all blocks together and exports the final obsplan.yaml"""
    
    dusk_time_nat, dusk_time_ast, dawn_time = calculate_wait_times(date_str, location, dawn_targets)
    
    plan = []
    
    # 1. Initialization & Dusk Prep
    plan.extend(write_start_sequence(dusk_time_nat))
    
    plan.append({'command': 'wait_until', 'ut': dusk_time_ast})
    
    plan.extend(write_focus_auto(range_start=37500, range_end=35500, step=200, alt=45.0, az=230.0, exptime=5.0))
    
    # 2. Dusk Target Loop
    plan.extend(write_observe_loop(dusk_targets, num_loops=dusk_loops))
    
    # 3. Dawn Wait & Safety Check
    plan.append({'command': 'wait_until', 'ut': dawn_time})
    plan.append({'command': 'check_observatory'})
    
    # Re-focus before dawn loop
    plan.extend(write_focus_auto(range_start=35500, range_end=37500, step=200, alt=45.0, az=120.0, exptime=5.0))
    
    # 4. Dawn Target Loop
    plan.extend(write_observe_loop(dawn_targets, num_loops=dawn_loops))
    
    # --- 5. Shutdown & Calibrations (UPDATED ORDER) ---
    plan.append({'command': 'park'})  # 1. Park the mount first to stop tracking
    plan.extend(write_calibrations(dusk_targets, dawn_targets, num_darks=9, num_biases=9)) # 2. Shoot calibrations
    plan.append({'command': 'end_sequence'}) # 3. Warm up cooler & turn off servers
    plan.append({'command': 'compress_data'}) # 4. Compress all data generated tonight (High CPU task)
    
    # --- 6. Formatted File Export ---
    filename = OBSPLAN_DIR / f"obsplan_{date_str.replace('-', '')}.yaml"
    
    raw_yaml = yaml.dump(plan, sort_keys=False, default_flow_style=False)
    formatted_yaml = raw_yaml.replace('\n- command:', '\n\n- command:')
    
    with open(filename, 'w') as file:
        file.write(formatted_yaml)
        
    print(f"✅ Successfully generated {filename}")
    print(f"   -> Dusk start (Nautical): {dusk_time_nat}")
    print(f"   -> Dusk start (Astronomical): {dusk_time_ast}")
    print(f"   -> Dawn start: {dawn_time}")

# ==========================================
# EXAMPLE USAGE
# ==========================================
if __name__ == "__main__":
    # Define your observatory location
    SRO_LOC = EarthLocation(lat=37.04 * u.deg, lon=-119.41 * u.deg, height=1400 * u.m)
    OBSPLAN_DIR = Path("obsplans")
    OBSPLAN_DIR.mkdir(exist_ok=True)
    
    # Define Evening Targets (Dusk)
    dusk_fields = [
        {'name': 'dusk_field1', 'ra': '10:44:27.33', 'dec': '+08:02:23.4', 'exptime': 60.0, 'iter': 3},
        {'name': 'dusk_field2', 'ra': '13:02:00.00', 'dec': '+10:00:00.0', 'exptime': 60.0, 'iter': 3}
    ]
    
    # Define Morning Targets (Dawn)
    dawn_fields = [
        {'name': 'dawn_field1', 'ra': '22:17:07.18', 'dec': '-09:55:56.1', 'exptime': 60.0, 'iter': 3},
        {'name': 'dawn_field2', 'ra': '21:40:22.04', 'dec': '-10:36:42.0', 'exptime': 60.0, 'iter': 3}
    ]
    
    generate_daily_yaml(
        date_str="2026-06-12",
        dusk_targets=dusk_fields,
        dawn_targets=dawn_fields,
        location=SRO_LOC,
        dusk_loops=16, 
        dawn_loops=16  
    )