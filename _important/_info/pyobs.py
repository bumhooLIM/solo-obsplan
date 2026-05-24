import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sys

import datetime

from astropy.coordinates import EarthLocation
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import get_sun
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun

# Degree - Float formating
def degree2float(angle):
    #angle : DD:MM:SS.SS

    #Check sign
    if angle[0] == "+":
        sign = +1
    elif angle[0] == "-":
        sign = -1
    else:
        sign = -1

    #Formating
    angle = angle.split(":")
    angle_float = abs(int(angle[0])) + int(angle[1])/60 + float(angle[2])/3600
    angle_float *= sign
    return angle_float

def float2degree(angle):
    #angle : float number

    #Check sign
    if angle >= 0:
        sign = "+"
    else:
        sign = "-"
    angle = abs(angle)

    #Formating
    DD = int(angle)
    MM = int((angle-DD)*60)
    SS = ((angle-DD)*60-MM)*60

    angle_degree = sign+f"{DD:02d}:{MM:02d}:{SS:010.7f}"
    
    return angle_degree

#Hour - Float formating
def hour2float(angle):
    #angle : +HH:MM:SS.SS

    #Check sign
    if angle[0] == "+" or angle[0] == "-":
        sign = angle[0]+"1"
    else:
        angle = "+"+angle
        sign = "+1"

    #Formating
    angle_float = int(angle[1:3]) + int(angle[4:6])/60 + float(angle[7:])/3600
    angle_float *= int(sign)
    return angle_float

def float2hour(angle):
    #angle : float number

    #Check sign
    if angle >= 0:
        sign = "+"
    else:
        sign = "-"
    angle = abs(angle)
    angle = angle
    
    #Formating
    HH = int(angle)
    MM = int((angle-HH)*60)
    SS = ((angle-HH)*60-MM)*60

    angle_hour = sign+f"{HH:02d}:{MM:02d}:{SS:010.7f}"
    return angle_hour

# Horizontal <-> Equitorial position
def horizon2equitorial(alt, az, format="text", latitude=37.5, longitude=128.5, t="now", mode = "hour"):
    #format
        # text: DD:MM:SS.SS
        # float: DD.DDDDDD
    #latitude & longitude default
        # latitude: +37.5
        # longitude: 128.5E (Western is negative value.)
    
    #Change Formating
    if format == "text":
        alt = degree2float(alt)
        az = degree2float(az)
    
    #Local Sidereal Time
    observing_location = EarthLocation(lat=latitude*u.deg, lon=longitude*u.deg)
    
    if t == "now":
        time = datetime.datetime.utcnow()
    else:
        time = t
        
    observing_time = Time(time, scale='utc', location=observing_location)
    lst = observing_time.sidereal_time('mean')
    lst = lst.degree
    
    #Degree to Radian
    LST = lst*np.pi/180
    ALT = alt*np.pi/180
    AZ = az*np.pi/180
    LAT = latitude*np.pi/180
    
    #Declination
    DEC = np.arcsin(np.cos(AZ)*np.cos(ALT)*np.cos(LAT)+np.sin(ALT)*np.sin(LAT))
    dec = DEC*180/np.pi
    
    #Hour Angle
    sinHA = -np.sin(AZ)*np.cos(ALT)/np.cos(DEC)
    cosHA = (-np.cos(AZ)*np.cos(ALT)*np.sin(LAT)+np.sin(ALT)*np.cos(LAT))/np.cos(DEC)
    
    HA = np.arctan2(sinHA,cosHA)
    ha = HA*180/np.pi
    
    #Right Ascension
    ra = lst - ha
    if ra<0:
        ra+=360
    elif ra>360:
        ra = ra%360
    
    #Formating result
    if mode == "hour":
        result = [float2hour(ra), float2degree(dec)]
    elif mode == "degree":
        result = [float2degree(ra), float2degree(dec)]
        
    return result

def equitorial2horizon(ra, dec, format="text", latitude=37.5, longitude=128.5, t="now", mode="hour"):
    #format
        # text: DD:MM:SS.SS
        # float: DD.DDDDDD
    #latitude & longitude default
        # latitude: +37.5
        # longitude: 128.5E (Western is negative value.)
    
    #Change Formating
    if format == "text" and mode == "hour":
        ra = hour2float(ra)/24*360
        dec = degree2float(dec)
    elif format == "text":
        ra = degree2float(ra)
        dec = degree2float(dec)
        
    #Local Sidereal Time
    observing_location = EarthLocation(lat=latitude*u.deg, lon=longitude*u.deg)
    
    if t == "now":
        time = datetime.datetime.utcnow()
    else:
        time = t
    
    observing_time = Time(time, scale='utc', location=observing_location)
    lst = observing_time.sidereal_time('mean')
    lst = lst.degree
    
    #Hour Angle
    ha = lst - ra
    if ha <0:
        ha += 360
    elif ha > 360:
        ha = ha%360
            
    #Degree to Radian
    RA = ra *np.pi/180
    DEC = dec*np.pi/180
    HA = ha*np.pi/180
    LAT = latitude*np.pi/180
    
    #Altitude
    sinALT = np.sin(LAT)*np.sin(DEC)+np.cos(LAT)*np.cos(DEC)*np.cos(HA)
    ALT = np.arcsin(sinALT)
    alt = ALT*180/np.pi
    
    #Azimuth
    cosAZ = (np.sin(DEC)*np.cos(LAT) - np.cos(DEC)*np.cos(HA)*np.sin(LAT))/np.cos(ALT)
    sinAZ = -np.cos(DEC)*np.sin(HA)/np.cos(ALT)
    AZ = np.arctan2(sinAZ, cosAZ)
    az = AZ*180/np.pi
    if az < 0:
        az += 360
    elif az >= 360:
        az = az%360
    
    #Formating result
    if format == "text":
        result = [float2degree(alt), float2degree(az)]
    elif format == "float":
        result = [alt, az]
        
    return result

def find_altaz(target, time = "now" , latitude=37.51120, longitude=126.97410):
    #Load pyobs
    python_setting = open("./_important/_info/python_setting.txt", encoding='utf-8')
    dir = python_setting.readline()
    sys.path.append(dir)
    python_setting.close()

    catalog = pd.read_csv(dir+"/deepsky_catalog.csv")
    if target[0] == "M":
        obj_type = "Messier"
    elif target[:2] == "IC":
        obj_type = "IC"
    elif target[:3] == "NGC":
        obj_type = "NGC"
    else:
        return "Please, enter with capital letter."
    
    if time == "now":
        time = datetime.datetime.utcnow()
    
    ra = "+" + catalog[catalog[obj_type]== target].iloc[0]["ra"] #hour
    dec = catalog[catalog[obj_type]== target].iloc[0]["dec"]
        
    alt, az = equitorial2horizon(ra, dec, latitude=latitude, longitude=longitude, t = time, mode="hour")
    return alt, az

def observability(target, start, end, interval = 10, latitude=37.51120, longitude=126.97410):
    start_time = int(start.strftime("%d"))*24*60 + int(start.strftime("%H"))*60 + int(start.strftime("%M"))
    end_time = int(end.strftime("%d"))*24*60 + int(end.strftime("%H"))*60 + int(end.strftime("%M"))
    
    n = (end_time - start_time)//interval
    
    T, alt, az = [], [], []
    for i in range(n):
        #inverse formatting
        time = start_time + interval * i
        dy = time//(24*60)
        time -= dy*24*60
        hr = time//60
        time -= hr*60
        mi = time

        #datetime format
        time = datetime.datetime.utcnow().replace(day = dy, hour = hr, minute = mi)
        
        #Calculate Horizontal Coordinate
        alt_temp, az_temp = find_altaz(target, time=time, latitude = latitude, longitude=longitude)
        alt_temp = degree2float(alt_temp)
        az_temp = degree2float(az_temp)
        
        T.append(time.strftime("%Y-%m-%d %H:%M:%S"))
        alt.append(alt_temp)
        az.append(az_temp)
        
    return T, alt, az

def plot_observability(target, start, end, interval = 10, latitude=37.51120, longitude=126.97410):
    
    T, alt, az = observability(target, start, end, interval = interval, latitude=latitude, longitude=longitude)
    
    solar_alt = []
    lunar_alt = []
    for t in range(len(T)):
        time = Time(T[t])
        location = EarthLocation.from_geodetic(lat=37.51120, lon=126.97410)
        frame = AltAz(obstime=time, location = location)
        sun = get_sun(time,).transform_to(frame)
        moon = get_body("moon", time).transform_to(frame)
        
        solar_alt.append(sun.alt.value)
        lunar_alt.append(moon.alt.value)
        
    plt.plot(T, alt, "k",label = target)
    plt.plot(T, lunar_alt, "y" ,label = "Moon")
    plt.xticks([T[0],T[len(T)//2] ,T[-1]])
    plt.yticks([-10, 10, 30, 50, 70, 90])
    plt.axhline(0, color = "gray", linestyle = "--")
    plt.ylabel("Altitude[deg]")
    plt.xlabel("Time")
    plt.grid(True)
    plt.ylim([-25, 95])
    plt.xlim([T[0], T[-1]])
    plt.fill_between(T,-25,95,np.array(solar_alt) > -18,color="gray",zorder=0, alpha=0.5)
    plt.fill_between(T,-25,95,np.array(solar_alt) > 0,color="gray",zorder=0)
    plt.legend()