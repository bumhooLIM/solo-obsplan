import argparse
from time import time
from time import strftime
from time import localtime

from alpaca.telescope import *
from alpaca.camera import *
from alpaca.focuser import *

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

# Equipment Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
t_IP = info[4].replace("[IP]: ","")
t_port = int(info[5].replace("[Port]: ",""))
c_IP = info[9].replace("[IP]: ","")
c_port = int(info[10].replace("[Port]: ",""))
f_IP = info[13].replace("[IP]: ","")
f_port = int(info[14].replace("[Port]: ",""))
equipment_info.close()

T = Telescope(t_IP, t_port)
C = Camera(c_IP, c_port)
F = Focuser(f_IP, f_port)

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Path
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
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

    Temperature = C.CCDTemperature
    Focus = F.Position

    #Equipment Status Announcement
    print("[LOCAL_TIME]:"+strftime('%Y-%m-%d %H:%M:%S', tm))
    print("[Mount]")
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
    print("[Camera]")
    print(f"[Temperature]: {Temperature:.2f}")
    print("[Focuser]")
    print(f"[Focus]: {Focus}")

    #Equipment Status Text
    equipment_status = open(Main_Path+"/output/equipment_status.txt", "w")
    equipment_status.write("LOCAL_TIME:"+strftime('%Y-%m-%d %H:%M:%S', tm)+"\n")
    equipment_status.write("[Mount]")
    equipment_status.write("[A Z]: "+AZ+"\n")
    equipment_status.write("[ALT]: "+ALT+"\n")
    equipment_status.write("[R A]: "+RA+"\n")
    equipment_status.write("[DEC]: "+DEC+"\n")
    equipment_status.write("\n")
    equipment_status.write("[Camera]"+"\n")
    equipment_status.write(f"[Temperature]: {Temperature:.2f}"+"\n")
    equipment_status.write("\n")
    equipment_status.write("[Focuser]"+"\n")
    equipment_status.write(f"[Focus]: {Focus}")
    equipment_status.close()

except Exception as e:
    print(local_time+f"FAIL : Loading equipment informations.\n")
    log.write(local_time+f"FAIL : Loading equipment informations.\n")
    log.write(local_time+"Error : "+str(e)+"\n")

#Log file
log.close()