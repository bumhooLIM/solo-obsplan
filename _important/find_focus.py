from time import time
from time import strftime
from time import localtime
from time import sleep

from alpaca.telescope import *
from alpaca.focuser import *

import warnings
warnings.filterwarnings('ignore')

from tqdm import tqdm
import numpy as np
from astropy.io import fits
from astropy.modeling import models, fitting
from astroquery.astrometry_net import AstrometryNet
import twirl
import astroalign as aa
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

import os
import sys

#Main Path
Main_Path = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

#Load pyobs
python_setting = open("./_important/_info/python_setting.txt", encoding='utf-8')
dir = python_setting.readline()
sys.path.append(dir)
python_setting.close()
import pyobs

#Telescope Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
IP = info[4].replace("[IP]: ","")
port = int(info[5].replace("[Port]: ",""))
equipment_info.close()
T = Telescope(IP, port)

#Focuser Adress & Connect
equipment_info = open(Main_Path+"/_important/_info/equipment_info.txt", 'r')
info = equipment_info.readlines()
IP = info[13].replace("[IP]: ","")
port = int(info[14].replace("[Port]: ",""))
equipment_info.close()
F = Focuser(IP, port)

#Time information
tm = localtime(time())
local_time = "["+strftime('%Y-%m-%d %H:%M:%S', tm) + "]  "

#Log file open
log = open(Main_Path+"/output/log_book.txt", 'a')

#Make image list
path = Main_Path+"/focus/"
img_list = []
for img_name in os.listdir(path):
    if img_name[-4:] == "fits" or img_name[-3:] == "fit":
        img_list.append(img_name)
img_list.sort()

#Crop Images & Check Focal position
crop_list = []
print("Cropping images...")
focus = []
for img_name in tqdm(img_list):
    img = fits.getdata(path + img_name)
    header = fits.getheader(path + img_name)

    n,m = np.shape(img)
    img = img[n//2 - n//4:n//2 + n//4, m//2 - m//4:m//2 + m//4]
    focus.append(header["FOCUS"])
    fits.writeto(path + img_name, img, header, overwrite=True)

#Align Images
print("Aligning images...")
for img_name in tqdm(img_list[1:]):
    ref_img = path + img_list[0]
    ref_data = fits.getdata(ref_img)

    target_data = fits.getdata(path + img_name)
    header = fits.getheader(path + img_name)
    try:
        aligned_image, footprint = aa.register(target_data, ref_data)
        fits.writeto(path + img_name, aligned_image, header, overwrite=True)
    except:
        print("Pass image: "+img_name)

#Exctract Star PSF
print("Find appropriate stars...")
star_imgs = [[], [], []]

img_name = img_list[0]
img = fits.getdata(path + img_name)
star_list = twirl.find_peaks(img)

star_num = []
for i in tqdm(range(len(star_list))):
    x0, y0 = star_list[i]
    x0, y0 = int(x0), int(y0)
    try:
        if np.max(img[y0-10:y0+10, x0-10:x0+10]) > 3000:
            pass
        else:
            star_num.append(i)
    except:
        pass
    if len(star_num)>2:
        break

print(f"Start PSF analysis with star number : {star_num[0]},{star_num[1]},{star_num[2]}")

for img_name in img_list[1:]:
    img = fits.getdata(path + img_name)
    for i in range(3):
        x0, y0 = star_list[star_num[i]]
        x0, y0 = int(x0), int(y0)
        star_imgs[i].append(img[y0-10:y0+10, x0-10:x0+10])

#Gaussian Fitting
sig_x = [[],[],[]]
sig_y = [[],[],[]]
for k in tqdm(range(3)):
    for j in range(len(star_imgs[k])):
        if len(star_imgs[k][j]) == 0:
            sig_x[k].append(np.nan)
            sig_y[k].append(np.nan)
            continue
        try:
            center = [int(np.mean(np.where(star_imgs[k][j] == np.max(star_imgs[k][j]))[0])), int(np.mean(np.where(star_imgs[k][j] == np.max(star_imgs[k][j]))[1]))]

            star_x = np.array(star_imgs[k][j][center[0]])
            star_y = np.array(star_imgs[k][j][:,center[1]])
            star_x -= int(np.min(star_x))
            star_y -= int(np.min(star_y))

            x, y = [], []
            for i in range(len(star_x)):
                x.append(i)
            for i in range(len(star_y)):
                y.append(i)
                
            # Fit the data using a Gaussian
            g_init_x = models.Gaussian1D(amplitude=np.max(star_x), mean=np.argmax(star_x), stddev=1.)
            g_init_y = models.Gaussian1D(amplitude=np.max(star_y), mean=np.argmax(star_y), stddev=1.)
            fit_g = fitting.TRFLSQFitter()
            g_x = fit_g(g_init_x, x, star_x)
            g_y = fit_g(g_init_y, y, star_y)
            
            if np.max(star_x)<1000:
                sig_x[k].append(np.nan)
                sig_y[k].append(np.nan)
            else:
                sig_x[k].append(g_x.stddev.value)
                sig_y[k].append(g_y.stddev.value)
                
        except Exception as e:
            print(f"Error in {j}-th image")
            print(e)
            sig_x[k].append(np.nan)
            sig_y[k].append(np.nan)

#Find Best Focal Position
sig_x_sorted = [[],[],[]]
sig_y_sorted = [[],[],[]]
focus_sorted = [[],[],[]]

for k in range(3):
    for i in range(len(sig_x[k])):
        if focus[i] in focus_sorted[k]:
            continue
        else:
            focus_sorted[k].append(focus[i])
            x_temp = []
            y_temp = []
            for j in range(len(focus[i:])-1):
                if focus[i:][j] == focus[i]:
                    if sig_x[k][i:][j] < 2:
                        x_temp.append(sig_x[k][i:][j])
                    if sig_y[k][i:][j] < 2:
                        y_temp.append(sig_y[k][i:][j])
            sig_x_sorted[k].append(np.mean(x_temp))
            sig_y_sorted[k].append(np.mean(y_temp))

def cosh(x, a, b, c):
    return a**2*(np.exp(-x+b)+np.exp(x-b))+c

focus_f = [[],[],[]]
fwhm_x = [[],[],[]]
fwhm_y = [[],[],[]]
best_focus = []
for k in range(3):    
    for i in range(len(focus_sorted[0])):
        if np.isnan(sig_x_sorted[k][i]) == False and np.isnan(sig_y_sorted[k][i]) == False:
            focus_f[k].append(focus_sorted[k][i]/1000)
            fwhm_x[k].append(sig_x_sorted[k][i])
            fwhm_y[k].append(sig_y_sorted[k][i])

    try:
        focus_range = [np.nanmin(focus_f[k]), np.nanmax(focus_f[k])]

        f = np.linspace(np.min(focus_f[k])-1, np.max(focus_f[k])+1, 100)

        popt_x, cov = curve_fit(cosh, focus_f[k], fwhm_x[k], p0 = [1, 17.5, 0.7])
        fwhm_x_plot = cosh(f, *popt_x)
        
        plt.plot(np.array(focus_f[k])*1000, fwhm_x[k], "r+", label = f"x fwhm data")
        plt.plot(f*1000, fwhm_x_plot, "r--")
        
        best_focus.append(popt_x[1]*1000)
        plt.plot(popt_x[1]*1000, cosh(popt_x[1], *popt_x), "ro", label = "best position (x)")
        
    except:
        pass
    
    try:
        popt_y, cov = curve_fit(cosh, focus_f[k], fwhm_y[k], p0 = [1, 17.5, 0.7])
        fwhm_y_plot = cosh(f, *popt_y)
        
        plt.plot(np.array(focus_f[k])*1000, fwhm_y[k], "b+", label = f"y fwhm data")
        plt.plot(f*1000, fwhm_y_plot, "b--")
        best_focus.append(popt_y[1]*1000)
        plt.plot(popt_y[1]*1000, cosh(popt_y[1], *popt_y), "bo", label = "best position (y)")
        
    except:
        pass
    
plt.xlabel("focus position")
plt.ylabel("fwhm[unit less]")
plt.savefig(Main_Path+'/auto_focus_result_'+strftime('%Y%m%d%H%M%S', tm)+".png")

try:
    print(f"The best focal position is {int(np.median(best_focus))}")
    log.write(local_time+f"The best focal position is {int(np.median(best_focus))}\n")
    print(f"Focus list: {best_focus}")
    answer = input(f"Do you want to adjust the focus to {int(np.median(best_focus))}?[y/n]")
    if answer == "y":
        try:
            F.Move(int(np.median(best_focus)))
            sleep(3)
            log.write(local_time+f"Move focus to {int(np.median(best_focus))}. Current focus : {F.Position} \n")
            print(local_time+f"Move focus to {int(np.median(best_focus))}. Current focus : {F.Position}")
        except Exception as e:
            log.write(local_time+f" FAIL : Move focus to {int(np.median(best_focus))}. \n")
            log.write(local_time+"Error : "+str(e)+"\n")
            print(local_time+f" FAIL : Move focus to {int(np.median(best_focus))}.")
except:
    log.write(local_time+'Auto-focusing Failed\n')
    print('Auto-focusing Failed')
    pass