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
exptime = 0.01
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
        C.StartExposure(exptime, False)
        while not C.ImageReady:
            sleep(0.5)

        img = C.ImageArray
        imginfo = C.ImageArrayInfo
        if imginfo.ImageElementType == ImageArrayElementTypes.Int32:
            if C.MaxADU <= 65535:
                imgDataType = np.uint16 # Required for BZERO & BSCALE to be written
            else:
                imgDataType = np.int32
        elif imginfo.ImageElementType == ImageArrayElementTypes.Double:
            imgDataType = np.float64

        if imginfo.Rank == 2:
            nda = np.array(img, dtype=imgDataType).transpose()
        else:
            nda = np.array(img, dtype=imgDataType).transpose(2,1,0)

        hdr = fits.Header()
        
        lt = localtime(time())
        hdr["LT"] = strftime('%Y-%m-%d %H:%M:%S', lt)
        utc = gmtime(time())
        utc = strftime('%Y-%m-%d %H:%M:%S', utc)
        jd = Time(utc, scale='utc').jd
        hdr["UTC"] = utc
        hdr["JD"] = jd
        hdr["EXPTIME"] = exptime
        hdr['XBINNING'] = C.BinX
        hdr['YBINNING'] = C.BinY
        hdr['CCDTEMP'] = C.CCDTemperature
        hdr['RA'] = pyobs.float2hour(T.RightAscension)
        hdr['DEC'] = pyobs.float2degree(T.Declination)
        hdr['ALT'] = pyobs.float2degree(T.Altitude)
        hdr['AZ'] = pyobs.float2degree(T.Azimuth)
        hdr['FOCUS'] = F.Position
        hdr['FOCALLEN'] = focal_length
        hdr['APTDIA'] = Diameter
        hdr['PIXSZ'] = pixel_size
        hdr['IMAGETYP'] = 'Bias'
        hdr['OBJECT'] = name #need to fix
        hdr['OBSERVAT'] = obs_name
        hdr["LON"] = obs_lon
        hdr["LAT"] = obs_lat
        hdr["ELAV"] = obs_elav
        hdr["OBSERVER"] = observer
        
        hdu = fits.PrimaryHDU(nda, header=hdr)
        hdu.writeto((name+f"_{i+1:03d}.fits").replace(" ", ""), overwrite=True)
        
    log.write(local_time+f"Bias {exptime:.1f}s*{iterations:03d}\n")
    print(local_time+f"Bias {exptime:.1f}s*{iterations:03d}")
except Exception as e:
    log.write(local_time+f"FAIL : Bias {exptime:.1f}s*{iterations:03d}\n")
    log.write(local_time+f"Error : "+str(e)+"\n")
    print(local_time+f"FAIL : Bias {exptime:.1f}s*{iterations:03d}")
    print(e)

#Log file
log.close()