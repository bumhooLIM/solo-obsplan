import argparse

from time import time
from time import strftime
from time import localtime
from time import gmtime
from time import sleep

import numpy as np
import pandas as pd

import astropy.io.fits as fits
from astropy.time import Time

from alpaca.camera import *
from alpaca.telescope import *
from alpaca.focuser import *

import os
import sys

#Plan interpreter
def plan_interpreter(df, index):
    if df["command"] == 'focus':
        command = "focus"
    elif df["command"] == 'focus auto':
        command = 'focus auto'
    elif df['command'] == 'goto rd':
        command = 'goto rd'
    elif df['command'] == 'goto aa':
        command = 'goto aa'
    elif df['command'] == 'exposure':
        command = 'exposure'
    elif df['command'] == 'flat':
        command = 'flat'
    elif df['command'] == 'dark':
        command = 'dark'
    elif df['command'] == 'bias':
        command = 'bias'

#Load pyobs
python_setting = open("./_info/python_setting.txt", encoding='utf-8')
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
t_name = info[1].replace("[Telescope]: ", "").replace("\n", "")
focal_length = info[2].replace("[Focal Length]: ", "").replace("\n", "")
Diameter = info[3].replace("[Diameter]: ", "").replace("\n", "")
c_name = info[7].replace("[Camera]: ", "").replace("\n", "")
pixel_size = info[8].replace("[Pixel Size]: ", "").replace("\n", "")
f_name = info[12].replace("[Focuser]: ", "").replace("\n", "")
equipment_info.close()

T = Telescope(t_IP, t_port)
C = Camera(c_IP, c_port)
F = Focuser(f_IP, f_port)

#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-f", "--file", dest="file", action="store",type=str)
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

filename = args.file
plan = pd.read_csv(Main_Path+'/'+filename)

status = 0

for i in range(len(plan)):
    if plan.iloc[i]["index"] == "sample":
        continue
    else:
        plan_interpreter(plan.iloc[i], int(plan.iloc[i]["index"]))
#Log file
log.close()