import argparse
from time import time
from time import strftime
from time import localtime

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

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Get the information
try:
    alt = T.Altitude
    az = T.Azimuth
    dec = T.Declination
    ra = T.RightAscension

    ALT = pyobs.float2degree(alt)
    AZ = pyobs.float2degree(az)
    DEC = pyobs.float2degree(dec)
    RA = pyobs.float2hour(ra)

    print("[LOCAL_TIME]:"+strftime('%Y-%m-%d %H:%M:%S', tm))
    if T.Tracking:
        print("[Tracking]: On")
    else:
        print("[Tracking]: Off")
        
    if T.AtPark:
        print("[Parking]: Parked")
    else:
        print("[Parking]: Unparked")
    print("[A Z]: "+AZ)
    print("[ALT]: "+ALT)
    print("[R A]: "+RA)
    print("[DEC]: "+DEC)
except Exception as e:
    print(local_time+f"FAIL : Loading mount informations.\n")
    log.write(local_time+f"FAIL : Loading mount informations.\n")
    log.write(local_time+"Error : "+str(e)+"\n")

#Log file
log.close()