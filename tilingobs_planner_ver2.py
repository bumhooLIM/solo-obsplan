from pathlib import Path
import kete
import numpy as np
import pandas as pd
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import skyloc as sloc
from astropy import units as u
from astroplan import Observer
from astropy.coordinates import (
    EarthLocation, AltAz, SkyCoord, get_sun, GeocentricTrueEcliptic, get_body
)
import warnings
from astropy.time import TimeDelta
from astroplan.exceptions import TargetNeverUpWarning, TargetAlwaysUpWarning
from tqdm import tqdm
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from astroplan import FixedTarget
from scipy.spatial.distance import cdist

###### CONFIGURATION - Please change as you wish ######
# Target selection
MIN_VMAG = 18 # Minimum V-band magnitude
MIN_ECL_LAT = -30.0 # Minimum ecliptic latitude  
MIN_LUNAR_DIST_DEG = 30.0   # e.g., keep targets >30° from the Moon
MIN_ABS_GAL_B_DEG  = 10.0   # e.g., |b| > 10° to avoid the Galactic plane
MIN_OBS_DUR = 1 # e.g., Observation duration longer than 1 hour
ALT_MIN = 30*u.deg # Minimum altitude

# Regions of interest (ROI)
CENTER_ELONG = 95 # \pm 95 degrees from the Sun
CENTER_LAT = 0 # Latitude of ROI center
ROI_LONG = 30 # \pm 15 degrees in longitude 
ROI_LAT = 20 # \pm 10 degrees in latitude

# Tiling
FOV = 3.0 # FOV of imager
MAX_FIELDS = 8 # Maximum number of fields
##########################END##########################

print('Download the orbit information file from JPL SBDB')
print('~ 4-10min for the first time, ~10s for subsequent runs.')
orb, m_ng = sloc.fetch_orb(
    output="orb_sbdb.parq",
    update_output=999,  # days - if output's last-modified is older than this, it will be updated
    filters=[
        # ("kind", "not in", ("au")),
        # ("kind", "in", ("cu", "cn")),
        ("condition_code", "in", ["0", "1"]),
    ]
)
print("Number of objects, number of columns: ", orb.shape)
print("latest 'soln_date' [US/Pacific]     : ", orb["soln_date"].max())

# Just for printing purposes...
n_ng = np.sum(m_ng)

print("Number of     grav objects          : ", orb.shape[0] - n_ng)
print("Number of non-grav objects          : ", n_ng)

#This part generates fov rectangle for dawn and dust observations

# 1) Get input from prompt
date_str = input("Enter date in YYYY-MM-DD (UT): ")
#date_str = '2025-09-03'

# Define observatory location
# lat [deg], lon [deg], height [km]
lat, lon, height = 37.071667, 240.58861, 1.400
location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=height*1000*u.m)

# Define observer
observer = Observer(location=location, timezone="UTC")

# Define midnight UT on the given date
t_midnight = Time(date_str + " 00:00:00", scale="utc")

# 2) Calculate next sunrise and sunset in UT
sunrise = observer.sun_rise_time(t_midnight, which="next")
sunset = observer.sun_set_time(t_midnight, which="next")
twil_morn_begin = observer.twilight_morning_nautical(t_midnight, which="next")
twil_eve_end    = observer.twilight_evening_nautical(t_midnight, which="next")

print(f"Sunrise (UT): {sunrise.iso}")
print(f"Sunset  (UT): {sunset.iso}")

# 3) Shift times: +3h after sunrise, -3h before sunset
sunrise_m3h = sunrise - 3*u.hour
#sunrise_m1h = sunrise - 1*u.hour

sunset_p3h = sunset + 3*u.hour
#sunset_p1h = sunset + 1*u.hour

# Convert to TDB Julian Dates
jd_tdb_sunrise = sunrise_m3h.tdb.jd
jd_tdb_sunset = sunset_p3h.tdb.jd

jd_tdb_obsbeg = twil_eve_end.tdb.jd
jd_tdb_obsend = twil_morn_begin.tdb.jd

#print(f"3h before sunrise (JD_TDB): {jd_tdb_sunrise}")
#print(f"3h after sunset (JD_TDB): {jd_tdb_sunset}")
#print(f"Ast. twilight starts (JD_TDB): {jd_tdb_obsbeg}")
#print(f"Ast. twilight ends (JD_TDB): {jd_tdb_obsend}")

# 4) Function to compute RA/Dec/Alt for λ☉±90°, β=0
def target_from_sun(time, location, offset_deg):
    # Sun position in ecliptic
    sun = get_sun(time)
    sun_ecl = sun.transform_to(GeocentricTrueEcliptic(equinox=time))
    lambda_target = sun_ecl.lon + offset_deg*u.deg
    beta_target = CENTER_LAT*u.deg
    
    target_ecl = SkyCoord(lon=lambda_target, lat=beta_target,
                          frame=GeocentricTrueEcliptic(equinox=time))
    
    # Convert to ICRS
    target_icrs = target_ecl.transform_to("icrs")
    
    # Alt/Az at observer
    altaz = target_icrs.transform_to(AltAz(obstime=time, location=location))
    
    return target_icrs.ra, target_icrs.dec, altaz.alt

# Sunset case (λ = λ☉ + 90°)
ra_sunset, dec_sunset, alt_sunset = target_from_sun(sunset_p3h, location, CENTER_ELONG)

# Sunrise case (λ = λ☉ - 90°)
ra_sunrise, dec_sunrise, alt_sunrise = target_from_sun(sunrise_m3h, location, -1*CENTER_ELONG)

# Assuming pos_au_sunset, vel_aupd_sunset, pos_au_sunrise, vel_aupd_sunrise
# are already obtained from your code / SPICE kernels

pos_au = np.array([0.0, 0.0, 0.0]) 
vel_aupd = np.array([0.0, 0.0, 0.0])

# Convert RA/Dec to degrees
ra_sunset_deg = ra_sunset.deg
dec_sunset_deg = dec_sunset.deg
ra_sunrise_deg = ra_sunrise.deg
dec_sunrise_deg = dec_sunrise.deg

# 3h after sunset FOV
obs_sunset, fov_sunset = sloc.fov.make_rect_fov(
    state_desig="SunsetObs",
    jd_tdb=sunset_p3h.tdb.jd,
    pos_au=pos_au,
    vel_aupd=vel_aupd,
    center_ra_deg=ra_sunset_deg,
    center_dec_deg=dec_sunset_deg,
    rotation_deg=0.0,
    lon_width_deg=ROI_LONG,  # example FOV size
    lat_width_deg=ROI_LAT  # we already point to anti-solar quadrature
)

# 3h before sunrise FOV
obs_sunrise, fov_sunrise = sloc.fov.make_rect_fov(
    state_desig="SunriseObs",
    jd_tdb=sunrise_m3h.tdb.jd,
    pos_au=pos_au,
    vel_aupd=vel_aupd,
    center_ra_deg=ra_sunrise_deg,
    center_dec_deg=dec_sunrise_deg,
    rotation_deg=0.0,
    lon_width_deg=ROI_LONG,
    lat_width_deg=ROI_LAT
)

fovs = sloc.FOVCollection([fov_sunrise, fov_sunset])
#fovs

# === 1.2M objs: ~30s on MBP 14" [2024, macOS 15.2, M4Pro(8P+4E/G20c/N16c/48G)]
# Initialize
print('Running SSOLocator...')
sl1 = sloc.SSOLocator(fovs=fovs, orb=orb, non_gravs=True)
#                                        ^^^^^^^^^^^^^^^
# Automatically use non-gravitational accelerations if parameters are available

# N-body propagate to mean JD of FOVs
# (later N-body simulations will be done *from* this JD0)
sl1.propagate_n_body(include_asteroids=False, jd0=np.mean)

# If you want, propag

# Check which FOVs contain which objects. dt_limit: 3 days (i.e., simple
# interpolation is used within 3 days and skips full N-body propagation)
sl1.fov_state_check(include_asteroids=False, dt_limit=3.)

fovc_hasobj1 = sloc.FOVCollection(sl1.fovc[sl1.fov_mask_hasobj])
orb_infov1 = sl1.orb.loc[sl1.orb_infov_mask].copy()

print(f"Number of ROIs with objects: {fovc_hasobj1.shape[0]} out of {len(fovs)}")
print(f"Number of objects in ROIs  : {orb_infov1.shape[0]}")

sl1.calc_ephems()

# The result is in sl1.eph (DataFrame)
eph = sl1.eph.copy()

# build coords and Moon positions at each epoch
obj = SkyCoord(ra=eph["ra"].to_numpy()*u.deg, dec=eph["dec"].to_numpy()*u.deg, frame="icrs")
moon_icrs = get_body("moon",t_midnight).icrs

# derive quantities and filter
eph["lunar_dist_deg"] = obj.separation(moon_icrs).deg
eph["gal_b"]          = obj.galactic.b.deg

def _isfinite_time(t: Time) -> bool:
    # robust finiteness test for astropy Time (scalar)
    return np.isfinite(t.jd)

def compute_ast_rising_setting(objs, observer, t_midnight, twil_eve_end, twil_morn_begin, horizon=ALT_MIN):
    """
    objs: iterable of targets (SkyCoord / FixedTarget)
    observer: astroplan.Observer
    t_midnight: Time near local midnight (UTC ok)
    twil_eve_end, twil_morn_begin: Time bounds for the night (astronomical twilight)
    """
    durations_hr = []

    # (optional) sanity: ensure we’re using the night that straddles t_midnight
    # twil_eve_end    = observer.twilight_evening_astronomical(t_midnight, which="previous")
    # twil_morn_begin = observer.twilight_morning_astronomical(t_midnight, which="next")

    for tgt in tqdm(objs, desc="Calculating Obs. Dur."):
        # Treat “never up/always up” warnings as non-finite results we handle
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rise_time = observer.target_rise_time(t_midnight, tgt, which="next", horizon=horizon)
            set_time  = observer.target_set_time (t_midnight, tgt, which="next", horizon=horizon)

            # If astroplan warned that the target never rises/sets, the times are NaN-like
            if any(issubclass(m.category, (TargetNeverUpWarning, TargetAlwaysUpWarning)) for m in w):
                durations_hr.append(0.0)
                continue

        # If either time is NaN, skip (some site/dec combos can yield NaN without warning in older versions)
        if not (_isfinite_time(rise_time) and _isfinite_time(set_time)):
            durations_hr.append(0.0)
            continue

        # Clip to your observing window
        start = max(rise_time, twil_eve_end)      # both Time
        end   = min(set_time,  twil_morn_begin)   # both Time
        dt = end - start                          # TimeDelta
        
        #print(rise_time, twil_eve_end, start, set_time, twil_morn_begin, end, dt)

        # No-overlap → zero
        durations_hr.append(max(dt.to_value("hour"), 0.0))
        #print(max(dt.to_value("hour"), 0.0))

    return durations_hr

eph_all = eph[
    (eph["vmag"] < MIN_VMAG) &
    (eph["dec"]  > MIN_ECL_LAT) 
]

obj = SkyCoord(ra=eph_all["ra"].to_numpy()*u.deg, dec=eph_all["dec"].to_numpy()*u.deg, frame="icrs")

observer = Observer(location=location, timezone="UTC") 
obs_duration = compute_ast_rising_setting(obj, observer, t_midnight, twil_eve_end, twil_morn_begin)

# OR, if eph_all already exists but came from a slice:
eph_all = eph_all.copy()

# then safe assignments
eph_all.loc[:, "dur"]            = obs_duration
eph_all.loc[:, "duration_flag"]  = (eph_all["dur"] > MIN_OBS_DUR).astype(int)
eph_all.loc[:, "lunar_flag"]     = (eph_all["lunar_dist_deg"] > MIN_LUNAR_DIST_DEG).astype(int)
eph_all.loc[:, "galactic_flag"]  = (np.abs(eph_all["gal_b"]) > MIN_ABS_GAL_B_DEG).astype(int)

# --- Separate sunrise and sunset FOVs ---
# The first FOV in the collection is sunrise, second is sunset
eph_sunrise = eph_all[eph_all["obsindex"] == 0]  # FOV index 0
eph_sunset  = eph_all[eph_all["obsindex"] == 1]  # FOV index 1

# Save to CSV
eph_sunrise.to_csv("dawn.csv", index=False)
eph_sunset.to_csv("dusk.csv", index=False)

# --- Use already defined location, sunrise_m3h, sunset_p3h, target_from_sun ---
# CSV files
csv_files = {"dawn": "dawn.csv", "dusk": "dusk.csv"}

# Parameters
fov_size = 3.0  # deg
alt_limit = 30  # degrees minimum altitude for observation
obs_duration_hours = 48  # simulate 12h for rising/setting

# --- Functions for reading, optimizing, plotting ---
def read_asteroids_from_csv(file_path, sun_ecl, lim=18.0):
    df = pd.read_csv(file_path)
    df_u = df
    df = df[df['vmag'] < lim]  # filter by magnitude
    df = df[(df["duration_flag"] == 1) &
    (df["lunar_flag"] == 1) &
    (df["galactic_flag"] == 1)]
    
    df_ud = df_u[(df_u['duration_flag'] == 0)]
    df_ul = df_u[(df_u['lunar_flag'] == 0)]
    df_ug = df_u[(df_u['galactic_flag'] == 0)]
 
    ra = df['ra'].values * u.deg
    dec = df['dec'].values * u.deg
    asteroid_ids = df['desig'].values
    asteroids = SkyCoord(ra=ra, dec=dec, frame='icrs', obstime=sun_ecl.obstime)
    asteroids_ecl = asteroids.transform_to(GeocentricTrueEcliptic)
    
    ra_ud = df_ud['ra'].values * u.deg
    dec_ud = df_ud['dec'].values * u.deg
    ud_asteroids = SkyCoord(ra=ra_ud, dec=dec_ud, frame='icrs', obstime=sun_ecl.obstime)
    ud_asteroids_ecl = ud_asteroids.transform_to(GeocentricTrueEcliptic)

    ra_ul = df_ul['ra'].values * u.deg
    dec_ul = df_ul['dec'].values * u.deg
    ul_asteroids = SkyCoord(ra=ra_ul, dec=dec_ul, frame='icrs', obstime=sun_ecl.obstime)
    ul_asteroids_ecl = ul_asteroids.transform_to(GeocentricTrueEcliptic)

    ra_ug = df_ug['ra'].values * u.deg
    dec_ug = df_ug['dec'].values * u.deg
    ug_asteroids = SkyCoord(ra=ra_ug, dec=dec_ug, frame='icrs', obstime=sun_ecl.obstime)
    ug_asteroids_ecl = ug_asteroids.transform_to(GeocentricTrueEcliptic)
    return asteroids_ecl, asteroid_ids, ud_asteroids_ecl, ul_asteroids_ecl, ug_asteroids_ecl

def optimize_fields(
    asteroids,
    asteroid_ids,
    fov_size=3.0,
    grid_step=0.2,
    max_fields=None,          # NEW: hard cap on number of fields to select
    strict=False              # NEW: if True, error when cap hit before full coverage
):
    """
    Optimize observation fields to cover asteroid positions with as few fields as possible.

    Parameters
    ----------
    asteroids : astropy.coordinates.SkyCoord
        Positions of asteroids to observe.
    asteroid_ids : numpy.ndarray
        IDs corresponding to the asteroids (same ordering as `asteroids`).
    fov_size : float, optional
        Square field-of-view size in degrees (edge-to-edge).
    grid_step : float, optional
        Grid step size for potential field placement (degrees).
    max_fields : int or None, optional
        Maximum number of fields to return. If None, no cap is applied.
    strict : bool, optional
        If True, raise a ValueError when `max_fields` is reached before covering
        all asteroids. If False, return the partial solution.

    Returns
    -------
    tuple
        (field_centers, field_asteroid_ids)
        field_centers: (N, 2) array of [RA_deg, Dec_deg] for each field center.
        field_asteroid_ids: list of lists of asteroid IDs covered by each field.

    Notes
    -----
    - Greedy selection:
      1) maximize newly covered asteroids
      2) tie-break by total covered (new + previously covered)
      3) tie-break by minimizing average distance to covered targets
    """
    # Transform asteroid positions to ICRS coordinates
    asteroid_eq = asteroids.transform_to('icrs')
    asteroid_positions = np.vstack([asteroid_eq.ra.deg, asteroid_eq.dec.deg]).T

    # Generate potential fields on a grid
    def generate_potential_fields(asteroids, grid_step=1.0):
        asteroid_eq = asteroids.transform_to('icrs')
        ap = np.vstack([asteroid_eq.ra.deg, asteroid_eq.dec.deg]).T
        min_ra = ap[:, 0].min() - 1
        max_ra = ap[:, 0].max() + 1
        min_dec = ap[:, 1].min() - 1
        max_dec = ap[:, 1].max() + 1
        ra_grid = np.arange(min_ra, max_ra, grid_step)
        dec_grid = np.arange(min_dec, max_dec, grid_step)
        ra_mesh, dec_mesh = np.meshgrid(ra_grid, dec_grid)
        return np.column_stack([ra_mesh.ravel(), dec_mesh.ravel()])

    potential_fields = generate_potential_fields(asteroids, grid_step)

    def is_covered(point, field, fov_size):
        return (abs(field[0] - point[0]) <= fov_size / 2 and
                abs(field[1] - point[1]) <= fov_size / 2)

    def calculate_average_distance(field, covered_indices, asteroid_positions):
        if not covered_indices:
            return float('inf')
        covered_positions = asteroid_positions[list(covered_indices)]
        distances = cdist(covered_positions, [field]).flatten()
        return float(np.mean(distances))

    # Initialize tracking
    fields = []
    field_asteroid_ids = []
    uncovered_indices = set(range(len(asteroid_positions)))

    # Greedy selection; now also respects the max_fields cap
    while uncovered_indices and (max_fields is None or len(fields) < max_fields):
        best_field = None
        best_newly_covered_indices = set()
        best_total_covered_indices = set()
        best_average_distance = float('inf')

        for pf in potential_fields:
            newly_covered_indices = {
                idx for idx in uncovered_indices
                if is_covered(asteroid_positions[idx], pf, fov_size)
            }
            if not newly_covered_indices:
                continue

            total_covered_indices = newly_covered_indices.union({
                idx for idx in range(len(asteroid_positions))
                if idx not in uncovered_indices and is_covered(asteroid_positions[idx], pf, fov_size)
            })

            update = False
            if len(newly_covered_indices) > len(best_newly_covered_indices):
                update = True
            elif len(newly_covered_indices) == len(best_newly_covered_indices):
                if len(total_covered_indices) > len(best_total_covered_indices):
                    update = True
                elif len(total_covered_indices) == len(best_total_covered_indices):
                    avg_dist = calculate_average_distance(pf, total_covered_indices, asteroid_positions)
                    if avg_dist < best_average_distance:
                        update = True

            if update:
                best_field = pf
                best_newly_covered_indices = newly_covered_indices
                best_total_covered_indices = total_covered_indices
                best_average_distance = calculate_average_distance(pf, best_total_covered_indices, asteroid_positions)

        if best_field is None:
            # No candidate field can add new coverage
            raise ValueError("Cannot cover additional asteroids with available field grid. "
                             "Consider reducing fov_size or grid_step, or check inputs.")

        fields.append(best_field)
        field_asteroid_ids.append(list(asteroid_ids[list(best_total_covered_indices)]))
        uncovered_indices -= best_newly_covered_indices

    # If we hit the cap with uncovered targets, decide based on `strict`
    if uncovered_indices and max_fields is not None and len(fields) >= max_fields:
        if strict:
            raise ValueError(
                f"Reached max_fields={max_fields} before covering all asteroids "
                f"(remaining: {len(uncovered_indices)})."
            )
        # else: return partial coverage silently

    return np.array(fields), field_asteroid_ids

def compute_rising_setting(fields, observer, obs_time, label, obsbeg, obsend, horizon=30*u.deg):
    rising_times, setting_times, flags = [], [], []

    for ra, dec in fields:
        target = FixedTarget(coord=SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs'))
        
        # Compute rise time
        rise_time = observer.target_rise_time(obs_time, target, which='next', horizon=horizon)
        
        if label == 'dawn' and rise_time > Time(obsend, format='jd', scale='tdb'):
            rise_time = '--'
            rising_times.append(rise_time)
        else:
            rising_times.append(rise_time.iso)

        # Compute set time
        set_time = observer.target_set_time(obs_time, target, which='next', horizon=horizon)
        #print(set_time.mask)

        if label == 'dusk' and set_time < Time(obsbeg, format='jd', scale='tdb'):
            set_time = '--'
            setting_times.append(set_time)
        else:
            setting_times.append(set_time.iso)

        flag = '1'

        if set_time == '--' or rise_time == '--' or set_time.mask or rise_time.mask:
            flag = '1' #Currently this function is not used. set 0 if you want to use this function.
        
        flags.append(flag)
        #print(flag, set_time, rise_time)

    return rising_times, setting_times, flags


def save_fov_csv(fields, field_ids, rising_times, setting_times, label, flags, filename, sort_by='rising'):

    ras = []
    decs = []

    for i, (ra, dec, set_time) in enumerate(zip(fields[:,0], fields[:,1], setting_times), start=1):
        coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
        ras.append(coord.ra.to_string(unit=u.hour, sep=':', precision=2, pad=True))
        decs.append(coord.dec.to_string(unit=u.deg, sep=':', precision=2, alwayssign=True, pad=True))
    
    df_out = pd.DataFrame({
        'index': np.arange(1, len(fields)+1),
        'ra[HH:MM:SS.SS]': ras,
        'dec[DD:MM:SS.SS]': decs,
        'exptime[s]': 60,
        'iterations' : 3,
        'rising_time': rising_times,
        'setting_time': setting_times,
        'asteroid_ids': field_ids,
        'obs_flag': flags
    })

    # Remove rows with unavailable times
    df_out = df_out[(df_out['obs_flag'] != '0')]

    # Sort by rising or setting time
    def parse_time(s):
        try:
            return Time(s).jd
        except:
            return np.inf

    if label == 'sunrise':
        df_out['sort_key'] = df_out['rising_time'].apply(parse_time)
    else:
        df_out['sort_key'] = df_out['setting_time'].apply(parse_time)

    df_out = df_out.sort_values(by='sort_key').drop(columns=['sort_key']).reset_index(drop=True)
    df_out['index'] = df_out.index + 1
    df_out.to_csv(filename, index=False)
    print(f"Saved CSV: {filename}")

def plot_observation(asteroids, fields, sun_ecl, asteroid_ids, flags, label, ud, ul, ug, fov_size=3.0, title="Tiling Observation Plan"):
    fig, ax = plt.subplots(figsize=(12,8))
    ax.set_aspect('equal')

    # Plot asteroids
    ax.scatter(asteroids.lon.deg, asteroids.lat.deg, color='red', s=30, label='Asteroids')
    ax.scatter(ud.lon.deg, ud.lat.deg, color='black', marker='x', s=30, label=f'Obs. Duration < {MIN_OBS_DUR}')
    ax.scatter(ul.lon.deg, ul.lat.deg, color='dimgray', marker='x', s=20, label=f'Lunar Dist. < {MIN_LUNAR_DIST_DEG}')
    ax.scatter(ug.lon.deg, ug.lat.deg, color='silver', marker='x', s=10, label=f'Gal. Lat. < {MIN_ABS_GAL_B_DEG}')

    # Colormap
    cmap = plt.get_cmap('rainbow', len(fields))  # Discrete colors for each field

    for i, field in enumerate(fields):
        fov_half = fov_size/2
        corners_eq = [
            SkyCoord(ra=(field[0]+fov_half)*u.deg, dec=(field[1]+fov_half)*u.deg, frame='icrs'),
            SkyCoord(ra=(field[0]-fov_half)*u.deg, dec=(field[1]+fov_half)*u.deg, frame='icrs'),
            SkyCoord(ra=(field[0]-fov_half)*u.deg, dec=(field[1]-fov_half)*u.deg, frame='icrs'),
            SkyCoord(ra=(field[0]+fov_half)*u.deg, dec=(field[1]-fov_half)*u.deg, frame='icrs')
        ]
        corners_ecl = [c.transform_to(GeocentricTrueEcliptic) for c in corners_eq]
        ecl_x = [c.lon.deg for c in corners_ecl] + [corners_ecl[0].lon.deg]
        ecl_y = [c.lat.deg for c in corners_ecl] + [corners_ecl[0].lat.deg]

        if flags[i] == '0':
            ls = ':'
        else:
            ls = '-'

        ax.plot(ecl_x, ecl_y, color=cmap(i), lw=2, label=f'Field {i+1}', ls=ls)

    ax.set_xlabel("Ecliptic Longitude [deg]")
    ax.set_ylabel("Ecliptic Latitude [deg]")
    ax.set_title(title)
    ax.legend(fontsize='small', ncol=2)
    plt.tight_layout()
    plt.savefig(f"{label}_{date_str}.png", dpi=300, bbox_inches='tight')


# --- Main loop for sunrise and sunset ---
for label, csv_file in csv_files.items():
    OPTIMIZE = True
    print(f'**Now working on {label} data**')
    obs_time = sunrise_m3h if label=="sunrise" else sunset_p3h
    sun_eq, sun_ecl = get_sun(obs_time), get_sun(obs_time).transform_to(GeocentricTrueEcliptic)
    asteroids, asteroid_ids, ud, ul, ug = read_asteroids_from_csv(csv_file, sun_ecl, lim=18.0)
    if len(asteroids) == 0:
        print("No asteroids after filtering; skipping optimization.")
        OPTIMIZE = False
    
    if OPTIMIZE:
        print('Optimizing fields...')
        fields, field_ids = optimize_fields(asteroids, asteroid_ids, fov_size=FOV, max_fields=MAX_FIELDS, strict=False)
    #strict=False       # set True to raise if limit is hit early

        observer = Observer(location=location, timezone="UTC")
        rising_times, setting_times, flags = compute_rising_setting(fields, observer, t_midnight, label, jd_tdb_obsbeg, jd_tdb_obsend)

        save_fov_csv(fields, field_ids, rising_times, setting_times, label, flags, f"{label}_{date_str}_FOV_plan.csv")
        plot_observation(asteroids, fields, sun_ecl, asteroid_ids, flags, label, ud, ul, ug, title=f"{label.capitalize()} Observation Plan")


