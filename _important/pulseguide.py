from alpaca.telescope import *
import argparse
from time import sleep
import os
import numpy as np

#Main Path
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

# Equipment Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
t_IP = info[4].replace("[IP]: ","")
t_port = int(info[5].replace("[Port]: ",""))

equipment_info.close()

T = Telescope(t_IP, t_port)

#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-t", "--time", dest="time", action="store")
args = parser.parse_args()

# #PulseGuide
guidetime = round(float(args.time))
T.GuideRateRightAscension = 1/3600
T.GuideRateDeclination = 1/3600

dec = T.Declination
ra_rate = 5 # round(11 / np.cos(dec*np.pi/180))
dec_rate = 100

for i in range(guidetime*10):
    # sleep(0.5 - ra_rate*0.001)
    # T.PulseGuide(GuideDirections.guideEast, Duration=ra_rate)
    sleep(1.0 - dec_rate*0.001)
    T.PulseGuide(GuideDirections.guideSouth, Duration=dec_rate)