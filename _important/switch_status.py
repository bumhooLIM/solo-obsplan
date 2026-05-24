import argparse

from time import time
from time import strftime
from time import localtime
from time import gmtime
from time import sleep

import numpy as np

import astropy.io.fits as fits
from astropy.time import Time

from alpaca.switch import *
from alpaca.telescope import GuideDirections

import os
import sys
import subprocess

S = Switch('127.0.0.1:11111', 0)

#Log file open
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
log = open(Main_Path+"/output/log_book.txt", 'a')

start, end = 1, 2

for i in range(start, end+1):
    try:
        if S.GetSwitch(i):
            print(f"[Port {i}]: On")
        else:
            print(f"[Port {i}]: Off")
    except:
        print(f"[Port {i}]: Fail to connect.")
        log.write(f"[Port {i}]: Fail to connect.")

log.close()

