import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime

from astropy.coordinates import EarthLocation, SkyCoord, AltAz, get_sun, get_body, Angle
from astropy.time import Time
from astropy import units as u

import directory # Utilizing your new centralized path manager

# --- Formatting Functions (Legacy Support) ---
# Astropy's 'Angle' object handles string parsing and formatting natively.
def degree2float(angle_str):
    return Angle(angle_str, unit=u.deg).deg

def float2degree(angle_float):
    return Angle(angle_float, unit=u.deg).to_string(unit=u.deg, sep=':', precision=2, pad=True)

def hour2float(angle_str):
    return Angle(angle_str, unit=u.hourangle).hour

def float2hour(angle_float):
    return Angle(angle_float, unit=u.hourangle).to_string(unit=u.hourangle, sep=':', precision=2, pad=True)

# --- Coordinate Transformations ---
def horizon2equatorial(alt, az, latitude=37.07167*u.deg, longitude=-119.41139*u.deg, height=1400*u.m, t="now"):
    """Converts Altitude/Azimuth to RA/Dec."""
    loc = EarthLocation(lat=latitude, lon=longitude, height=height)
    obstime = Time.now() if t == "now" else Time(t)
    
    # Define the point in the sky using Alt/Az
    coord = SkyCoord(alt=alt*u.deg, az=az*u.deg, frame=AltAz(obstime=obstime, location=loc))
    
    # Transform to standard Equatorial (ICRS)
    eq = coord.transform_to('icrs')
    return eq.ra.hour, eq.dec.deg

def equatorial2horizon(ra, dec, latitude=37.07167*u.deg, longitude=-119.41139*u.deg, height=1400*u.m, t="now"):
    """
    Converts RA/Dec to Altitude/Azimuth.
    Automatically handles string inputs ("HH:MM:SS", "DD:MM:SS") or floats.
    """
    loc = EarthLocation(lat=latitude, lon=longitude, height=height)
    obstime = Time.now() if t == "now" else Time(t)
    
    # Astropy SkyCoord intelligently parses strings vs floats if you give it the right units
    coord = SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
    
    altaz = coord.transform_to(AltAz(obstime=obstime, location=loc))
    
    # Returning raw float values is much cleaner for logical comparisons downstream
    return altaz.alt.deg, altaz.az.deg

# # --- Catalog Search ---
# def find_altaz(target, time="now", latitude=37.07167*u.deg, longitude=-119.41139*u.deg, height=1400*u.m):
#     catalog_path = directory.INFO_DIR / "deepsky_catalog.csv"
#     catalog = pd.read_csv(catalog_path)
    
#     if target.startswith("M"):
#         obj_type = "Messier"
#     elif target.startswith("IC"):
#         obj_type = "IC"
#     elif target.startswith("NGC"):
#         obj_type = "NGC"
#     else:
#         raise ValueError("Target prefix not recognized. Use M, IC, or NGC.")
    
#     target_data = catalog[catalog[obj_type] == target].iloc[0]
    
#     # Assuming catalog format is string "+HH:MM:SS" and float/string dec
#     ra = target_data["ra"]
#     dec = target_data["dec"]
    
#     if not str(ra).startswith("+") and not str(ra).startswith("-"):
#         ra = "+" + str(ra)
        
#     return equatorial2horizon(ra, dec, latitude=latitude, longitude=longitude, height=height, t=time)

# # --- Observability & Plotting ---
# def plot_observability(target, start_time, end_time, interval_minutes=10, latitude=37.07167*u.deg, longitude=-119.41139*u.deg, height=1400*u.m):
#     """
#     Plots the target's altitude over time against Solar and Lunar constraints.
#     Now fully vectorized: Calculates hundreds of points instantly without loops.
#     """
#     loc = EarthLocation(lat=latitude, lon=longitude, height=height)
    
#     start_t = Time(start_time)
#     end_t = Time(end_time)
    
#     # Create an array of times (vectorization)
#     time_diff = (end_t - start_t).sec
#     intervals = np.arange(0, time_diff, interval_minutes * 60)
#     times = start_t + intervals * u.second
    
#     # Target Setup
#     try:
#         catalog_path = directory.INFO_DIR / "deepsky_catalog.csv"
#         catalog = pd.read_csv(catalog_path)
#         # Simplify targeting logic
#         obj_type = "Messier" if target.startswith("M") else "IC" if target.startswith("IC") else "NGC"
#         target_data = catalog[catalog[obj_type] == target].iloc[0]
        
#         ra = "+" + str(target_data["ra"]) if not str(target_data["ra"]).startswith(("+", "-")) else str(target_data["ra"])
#         dec = target_data["dec"]
#         target_coord = SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
#     except Exception as e:
#         print(f"Failed to find {target}: {e}")
#         return

#     # Calculate all Alt/Az frames simultaneously
#     frame = AltAz(obstime=times, location=loc)
#     target_altaz = target_coord.transform_to(frame)
#     sun_altaz = get_sun(times).transform_to(frame)
#     moon_altaz = get_body("moon", times).transform_to(frame)
    
#     # Plotting
#     plot_times = times.datetime
#     plt.figure(figsize=(10, 5))
#     plt.plot(plot_times, target_altaz.alt.deg, "k", label=target)
#     plt.plot(plot_times, moon_altaz.alt.deg, "y", label="Moon")
    
#     plt.axhline(0, color="gray", linestyle="--")
#     plt.ylabel("Altitude [deg]")
#     plt.xlabel("Time (UT)")
#     plt.title(f"Observability of {target}")
#     plt.grid(True)
#     plt.ylim([-25, 95])
#     plt.xlim([plot_times[0], plot_times[-1]])
    
#     # Twilight shading
#     plt.fill_between(plot_times, -25, 95, sun_altaz.alt.deg > -18, color="gray", zorder=0, alpha=0.3, label="Twilight")
#     plt.fill_between(plot_times, -25, 95, sun_altaz.alt.deg > 0, color="lightblue", zorder=0, alpha=0.5, label="Daylight")
    
#     plt.legend()
#     plt.tight_layout()
#     plt.show()