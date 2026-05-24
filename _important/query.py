import argparse
from time import time
from time import strftime
from time import localtime

import logging

import numpy as np

from astropy.coordinates import EarthLocation
from astropy.time import Time
from astropy import units as u
import astropy.io.fits as fits
from astropy.coordinates import SkyCoord
from astropy import wcs

from alpaca.telescope import *

import os
import sys

from astroquery.astrometry_net import AstrometryNet
from astroquery.astrometry_net import conf

import warnings
import logging

warnings.filterwarnings('ignore', module='astroquery.astrometry_net')
logging.getLogger('astroquery.astrometry_net').setLevel(logging.ERROR)

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

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Argparse
parser = argparse.ArgumentParser()
parser.add_argument("-i", "--img", dest="img", action="store")
args = parser.parse_args()

#Query
conf.api_key = 'vkqlusbdvvbbgwlq'
AstrometryNet.key = 'vkqlusbdvvbbgwlq'
ast = AstrometryNet()

img_name = args.img
hdulist = fits.open(img_name)
try:
    wcs_header = ast.solve_from_image(img_name)
    
    w = wcs.WCS(wcs_header)

    hdulist = fits.open(img_name)
    img = hdulist[0].data
    n, m = np.shape(img)

    ra_q, dec_q = w.wcs_pix2world([[n//2, m//2]], 0)[0]
    ra_q = ra_q *24/360
    center = [ra_q, dec_q]
    center_txt = [pyobs.float2hour(ra_q),pyobs.float2degree(dec_q)]

    try:
        answer = input("Do you want to sync with position RA :"+center_txt[0]+", DEC :"+center_txt[1]+"?[y/n]")
        if answer == "y":
            T.SyncToCoordinates(center[0], center[1])
            log.write(local_time+f"Sync to RA:"+center_txt[0]+" DEC:"+center_txt[1]+"\n")

    except Exception as e:
        log.write(local_time+f"FAIL : Sync to RA:"+center_txt[0]+" DEC:"+center_txt[1]+"\n")
        log.write(local_time+"Error : "+str(e)+"\n")
        print(local_time+f"FAIL : Sync to RA:"+center_txt[0]+" DEC:"+center_txt[1])

except Exception as e:
    log.write(local_time + "Fail : Query Image "+img_name)
    print(local_time + "Fail : Query Image")
    print(e)