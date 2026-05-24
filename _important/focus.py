import argparse
from time import time
from time import strftime
from time import localtime
from time import sleep
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

#Focuser Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
IP = info[13].replace("[IP]: ","")
port = int(info[14].replace("[Port]: ",""))
equipment_info.close()
F = Focuser(IP, port)

#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-f", "--dx", dest="dx", action="store")
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#ALT/AZ formating
dx = int(args.dx)

if dx != 0:
    #Adjust Focus
    try:
        F.Move(dx+F.Position)

        sleep(3)
        log.write(local_time+f"Move focus {dx}. Current focus : {F.Position} \n")
        print(local_time+f"Move focus {dx}. Current focus : {F.Position}")
    except Exception as e:
        log.write(local_time+f" FAIL : Move focus {dx}. \n")
        log.write(local_time+"Error : "+str(e)+"\n")
        print(local_time+f" FAIL : Move focus {dx}.")
else:
    #Announce Focus
    try:
        print(local_time+f"Current focus : {F.Position}")
    except Exception as e:
        log.write(local_time+f" FAIL : Check Focus. \n")
        log.write(local_time+"Error : "+str(e)+"\n")
        print(local_time+f" FAIL : Check Focus.")

#Log file
log.close()