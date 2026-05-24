import argparse
from time import time
from time import strftime
from time import localtime
from time import sleep
from alpaca.telescope import *


import os
import sys


#Load pyobs
python_setting = open("./_important/_info/python_setting.txt", encoding='utf-8')
dir = python_setting.readline()
sys.path.append(dir)
python_setting.close()
import pyobs


#Main Path
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))


#Telescope Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
IP = info[4].replace("[IP]: ","")
port = int(info[5].replace("[Port]: ",""))
equipment_info.close()
T = Telescope(IP, port)


#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-d", "--direction", dest="direction", action="store")
parser.add_argument("-a", "--amp", dest="amp", action="store")
parser.add_argument("-u", "--unit", dest="unit", action="store")
args = parser.parse_args()


#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "


#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')


#RA/DEC formating
amplitude = float(args.amp)
axis = args.direction
unit = args.unit


#Go-To
try:
    alt = T.Altitude
    az = T.Azimuth
    dec = T.Declination
    ra = T.RightAscension


    T.Unpark()
    T.Tracking = True


    if unit == 'h' or  unit == "d":
        amplitude = amplitude
    elif unit == 'm':
        amplitude = amplitude/60
    elif unit == 's':
        amplitude = amplitude/3600


    if axis == "ra":
        ra = ra+amplitude
        while True:
            if ra<0:
                ra += 24
            elif ra>24:
                ra -= 24
            else:
                break
        T.SlewToCoordinatesAsync(ra, dec)

    elif axis == "dec":
        dec = dec+amplitude
        while True:
            if dec<-90:
                dec = -180 - dec
                ra = 24 - ra
            elif dec>90:
                dec = 180 - dec
                ra = 24 - ra
            else:
                break
        T.SlewToCoordinatesAsync(ra, dec)

    elif axis == "alt":
        alt = alt+amplitude
        while True:
            if alt<-90:
                alt = - 180 - alt
            elif alt>90:
                alt = 180 - alt
            else:
                break
        T.SlewToAltAzAsync(az, alt)

    elif axis == "az":
        az = az+amplitude
        while True:
            if az<0:
                az += 360
            elif az>360:
                az -= 360
            else:
                break
        T.SlewToAltAzAsync(az, alt)

    if axis == "ra" or axis == "dec":
        RA = pyobs.float2hour(ra)
        DEC = pyobs.float2degree(dec)
        log.write(local_time+f"Go-to RA: "+RA+" DEC: "+DEC+"\n")
        print(local_time+f"Go-to RA: "+RA+" DEC: "+DEC)

    elif axis == "alt" or axis == "az":
        ALT = pyobs.float2degree(alt)
        AZ = pyobs.float2degree(az)
        log.write(local_time+f"Go-to ALT: "+ALT+" AZ: "+AZ+"\n")
        print(local_time+f"Go-to ALT: "+ALT+" AZ: "+AZ)


except Exception as e:
    if axis == "ra" or axis == "dec":
        RA = pyobs.float2degree(ra)
        DEC = pyobs.float2degree(dec)
        log.write(local_time+f"[FAIL]Go-to RA: "+RA+" DEC: "+DEC+"\n")
        print(local_time+f"[FAIL]Go-to RA: "+RA+" DEC: "+DEC)
    elif axis == "alt" or axis == "az":
        ALT = pyobs.float2degree(alt)
        AZ = pyobs.float2degree(az)
        log.write(local_time+f"[FAIL]Go-to ALT: "+ALT+" AZ: "+AZ+"\n")
        print(local_time+f"[FAIL]Go-to ALT: "+ALT+" AZ: "+AZ)


#Log file
log.close()