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

#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store")
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Cooler Switch
switch = args.switch

try:
    if switch == "on":
        C.CoolerOn = True
        log.write(local_time+" Cooler On\n")
        print(local_time+" Cooler On")
    elif switch == "off":
        C.CoolerOn = False
        log.write(local_time+" Cooler Off\n")
        print(local_time+" Cooler Off")

except Exception as e:
    if switch == "on":
        log.write(local_time+"FAIL : Cooler On\n")
        print(local_time+"FAIL : Cooler On")
    elif switch == "off":
        log.write(local_time+"FAIL : Cooler Off\n")
        print(local_time+"FAIL : Cooler Off")      
    log.write(local_time+"Error : "+str(e)+"\n")  

#Log file
log.close()