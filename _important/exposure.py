import argparse

from time import time
from time import strftime
from time import localtime
from time import gmtime
from time import sleep

import numpy as np

import astropy.io.fits as fits
from astropy.time import Time

from alpaca.camera import *
from alpaca.telescope import *
from alpaca.focuser import *
from alpaca.telescope import GuideDirections

import os
import sys
import subprocess

#Load pyobs
python_setting = open("./_important/_info/python_setting.txt", encoding='utf-8')
dir = python_setting.readline()
sys.path.append(dir)
python_setting.close()
import pyobs

#Main Path
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

#DS9 Path
ds9_path = "C:\\SAOImageDS9\\ds9.exe"

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

# Observatory Info
observatory_info = open(Main_Path+"/_important/_info/observatory_info.txt", 'r')
info = observatory_info.readlines()
obs_name = info[0].replace("[Name]: ", "").replace("\n", "")
obs_lon = info[1].replace("[Longitude]: ", "").replace("\n", "")
obs_lat = info[2].replace("[Latitude]: ", "").replace("\n", "")
obs_elav = info[3].replace("[Elevation]: ", "").replace("\n", "")
observatory_info.close()

# Observer Info
observer_info = open(Main_Path+"/_important/_info/observer.txt", 'r')
info = observer_info.readlines()
observer = info[0]
observer_info.close()

#Argparse setting
parser = argparse.ArgumentParser()
parser.add_argument("-n", "--name", dest="name", action="store")
parser.add_argument("-t", "--time", dest="time", action="store")
parser.add_argument("-i", "--iter", dest="iter", action="store")
parser.add_argument("-x", "--xbin", dest="xbin", action="store")
parser.add_argument("-y", "--ybin", dest="ybin", action="store")
args = parser.parse_args()

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Cooler Switch
name = args.name
exptime = float(args.time)
iterations = int(args.iter)

#Exposure
try:
    for i in range(iterations):
        C.BinX = int(args.xbin)
        C.BinY = int(args.ybin)
        C.StartX = 0
        C.StartY = 0
        C.NumX = C.CameraXSize // C.BinX
        C.NumY = C.CameraYSize // C.BinY

        hdr = fits.Header()
        
        utc = gmtime(time())
        utc = strftime('%Y-%m-%d %H:%M:%S', utc)
        jd = Time(utc, scale='utc').jd
        hdr["UTC-STA"] = utc

        C.StartExposure(exptime, True)
        exp_duration = 0
        while not C.ImageReady:
            sleep(0.5)
            if exp_duration > exptime:
                break
            exp_duration += 0.4


        img = C.ImageArray
        imginfo = C.ImageArrayInfo
        imgDataType = np.uint16

        if imginfo.Rank == 2:
            nda = np.array(img, dtype=imgDataType).transpose()
        else:
            nda = np.array(img, dtype=imgDataType).transpose(2,1,0)
        
        lt = localtime(time())
        hdr["LT"] = strftime('%Y-%m-%d %H:%M:%S', lt)
        utc = gmtime(time())
        utc = strftime('%Y-%m-%d %H:%M:%S', utc)
        jd = Time(utc, scale='utc').jd
        hdr["UTC-END"] = utc
        hdr["JD"] = jd
        hdr["EXPTIME"] = f'{exptime:.3f}'
        hdr['XBINNING'] = C.BinX
        hdr['YBINNING'] = C.BinY
        hdr['CCDTEMP'] = C.CCDTemperature
        hdr["GAIN"] = C.Gain
        hdr["LOWGAIN"] = 2.8
        hdr["EPADU"] = C.ElectronsPerADU
        hdr['RA'] = pyobs.float2hour(T.RightAscension)
        hdr['DEC'] = pyobs.float2degree(T.Declination)
        hdr['ALT'] = pyobs.float2degree(T.Altitude)
        hdr['AZ'] = pyobs.float2degree(T.Azimuth)
        hdr['FOCUS'] = F.Position
        hdr['FOCALLEN'] = focal_length
        hdr['APTDIA'] = Diameter
        hdr['PIXSZ'] = pixel_size
        hdr['FILTER'] = "NONE"
        hdr['IMAGETYP'] = 'Light'
        hdr['OBJECT'] = name #need to fix
        hdr['OBSERVAT'] = obs_name
        hdr["LON"] = obs_lon
        hdr["LAT"] = obs_lat
        hdr["ELAV"] = obs_elav
        hdr["OBSERVER"] = observer
        
        hdu = fits.PrimaryHDU(nda, header=hdr)
        utc = gmtime(time())
        img_name = (name+f"_{i+1:03d}_"+strftime('%Y%m%d%H%M%S', utc)+".fits").replace(" ", "")
        hdu.writeto(img_name, overwrite=True)
        print(f"Median: {np.median(nda)}, Min: {np.min(nda)}, Max: {np.max(nda)}")
        # sleep(45)

        prev_img = open("./_important/_info/prev_img.txt", "w")
        prev_img.write(img_name)
        prev_img.close()

        try:
            subprocess.run(
                ["taskkill", "/IM", "ds9.exe", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True
            )
        except:
            pass
        try:
            subprocess.Popen([ds9_path, img_name, "-geometry", "600x600+1100+0","-zoom", "to", "fit"])
        except:
            print("[FAIL]: open ds9")

    log.write(local_time+f"Exposure {exptime:.3f}s*{iterations:03d}\n")
    print(local_time+f"Exposure {exptime:.3f}s*{iterations:03d}")

    
    
except Exception as e:
    log.write(local_time+f"FAIL : Exposure {exptime:31f}s*{iterations:03d}\n")
    log.write(local_time+f"Error : "+str(e)+"\n")
    print(local_time+f"FAIL : Exposure {exptime:.3f}s*{iterations:03d}")
    print(e)

dark_list = open("./_important/_info/dark_list.txt", "r")
dark_exptimes = []
for line in dark_list.readlines():
    if "Dark List" in line:
        continue
    else:
        dark_exptimes.append(float(line.replace("\n", "")))

dark_list.close()

if exptime not in dark_exptimes:
    dark_list = open("./_important/_info/dark_list.txt", "a")
    dark_list.write(f"{round(exptime):03d}\n")
    dark_list.close()

#Log file
log.close()