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

#Argparse
parser = argparse.ArgumentParser()
parser.add_argument("-p", "--parking", dest="command", action="store")
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file
log = open(Main_Path+"/output/log_book.txt", 'a')

#Commands
if args.command == "park":
    try:
        T.Park()
        log.write(local_time+"Parked telescope.\n")
        print(local_time+"Parked telescope.")
    except Exception as e:
        log.write(local_time+"FAIL : Parked telescope.\n")
        log.write(local_time+"Error : "+str(e)+"\n")
        print(local_time+"FAIL : Parked telescope.")
        
elif args.command == "unpark":
    try:
        T.Unpark()
        log.write(local_time+"Unparked telescope.\n")
        print(local_time+"Unparked telescope.")
    except Exception as e:
        log.write(local_time+"FAIL : Unparked telescope.\n")
        log.write(local_time+"Error : "+str(e)+"\n")
        print(local_time+"FAIL : Unparked telescope.")
   
#Log file
log.close()