from time import time
from time import strftime
from time import localtime
from time import sleep

from alpaca.telescope import *

import numpy as np
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

# Observatory Info
observatory_info = open(Main_Path+"/_important/_info/observatory_info.txt", 'r')
info = observatory_info.readlines()
obs_name = info[0].replace("[Name]: ", "").replace("\n", "")
obs_lon = info[1].replace("[Longitude]: ", "").replace("\n", "")
obs_lat = info[2].replace("[Latitude]: ", "").replace("\n", "")
obs_elav = info[3].replace("[Elavation]: ", "").replace("\n", "")
observatory_info.close()

lon = pyobs.degree2float(obs_lon)
lat = pyobs.degree2float(obs_lat)

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file
log = open(Main_Path+"/output/log_book.txt", 'a')

#Commands
#Open Cluster List
open_cluster = ["M6", "M7", "M11", "M16", "M18", "M21", "M23", "M24", "M25", "M26", "M34", "M35", "M36", "M37", "M38", "M39", "M41", "M44", "M45", "M46", "M47", "M48", "M50", "M52", "M67", "M93", "M103"]

alt = []
az = []
for obj in open_cluster:
    alt_temp, az_temp = pyobs.find_altaz(obj, longitude=lon, latitude=lat)
    alt.append(pyobs.degree2float(alt_temp))
    az.append(pyobs.degree2float(az_temp))

highest_index = np.where(alt == np.max(alt))
highest_index = highest_index[0][0]

print(f"Highest Open cluster is "+open_cluster[highest_index]+".")
answer = input("Do you want to go to "+open_cluster[highest_index]+f"?[y/n]\nalt: {alt[highest_index]:.2f}, az: {az[highest_index]:.2f}\n")

az = az[highest_index]
alt = alt[highest_index]
ALT = pyobs.float2degree(alt)
AZ = pyobs.float2degree(az)

if answer == "y":
    #Go-to
    try:
        T.Unpark()
        T.Tracking = False
        T.SlewToAltAzAsync(az, alt)
        sleep(3)
        log.write(local_time+f"Go-to ALT: "+ALT+" AZ: "+AZ+"\n")
        print(local_time+f"Go-to ALT: "+ALT+" AZ: "+AZ+"\n")
    except Exception as e:
        log.write(local_time+f"FAIL : Go-to ALT: "+ALT+" AZ: "+AZ+"\n")
        log.write(local_time+"Error : "+str(e)+"\n")

#Log file
log.close()