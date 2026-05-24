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
parser.add_argument("-a", "--alt", dest="alt", action="store")
parser.add_argument("-z", "--az", dest="az", action="store")
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#RA/DEC formating
alt = float(args.alt)
az = float(args.az)
ALT = pyobs.float2degree(alt)
AZ = pyobs.float2degree(az)

#Go-to
try:
    T.Unpark()
    T.Tracking = False
    T.SyncToAltAz(az, alt)
    log.write(local_time+f"Sync to ALT:"+ALT+" AZ:"+AZ+"\n")
    print(local_time+f"Sync to ALT:"+ALT+" AZ:"+AZ)
except Exception as e:
    log.write(local_time+f"FAIL : Sync to ALT:"+ALT+" AZ:"+AZ+"\n")
    log.write(local_time+"Error : "+str(e)+"\n")
    print(local_time+f"FAIL : Sync to ALT:"+ALT+" AZ:"+AZ)

#Log file
log.close()