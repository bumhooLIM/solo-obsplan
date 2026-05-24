import argparse
from time import time
from time import strftime
from time import localtime
from alpaca.camera import *

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

#Camera Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
IP = info[9].replace("[IP]: ","")
port = int(info[10].replace("[Port]: ",""))
equipment_info.close()
C = Camera(IP, port)

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Announce
try:
    print(f"[CCD Temperature]: {C.CCDTemperature:.2f}K")
    print(f"[Cooler Power]: {C.CoolerPower:.2f}%")
    if C.CoolerOn:
        print("[Cooler]: On")
    else:
        print("[Cooler]: Off")
    log.write(local_time + "Announce Camera Status")
except Exception as e:
    log.write(local_time + "Fail : Announce Camera Status")
    print(local_time + "Fail : Announce Camera Status")

#Log file
log.close()