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

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--switch", dest="switch", action="store")
args = parser.parse_args()

#Log file open
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
log = open(Main_Path+"/output/log_book.txt", 'a')

start, end = 1, 2

if args.switch == "on":
    for i in range(start, end + 1):
        try:
            S.SetSwitch(i, True)
            log.write(f"Turn on switch-{i}.\n")
        except:
            print(f"False to turn on switch-{i}.")
            log.write(f"False to turn on switch-{i}.\n")
elif args.switch == "off":
    for i in range(start, end+1):
        try:
            S.SetSwitch(i, False)
            log.write(f"Turn on switch-{i}.\n")
        except:
            print(f"False to turn off switch-{i}.")
            log.write(f"False to turn off switch-{i}.\n")


log.close()

