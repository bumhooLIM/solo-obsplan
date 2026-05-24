#Library
import typer
from pyfiglet import Figlet

import sys
import os
import subprocess

import pandas as pd

from time import sleep

#Load pyobs
python_setting = open("./_important/_info/python_setting.txt", encoding='utf-8')
dir = python_setting.readline()
sys.path.append(dir)
python_setting.close()
import pyobs

#App
app = typer.Typer()

### Basic Functions
#Login
@app.command()
def log_in():
    f = Figlet(font = 'slant')
    print(f.renderText('RASA11 Controller'))

    observer = typer.prompt("Observer")
    typer.echo("\nHello, "+observer+"!")
    return observer

#Help
@app.command()
def help(mode):
    help_txt = open("./_important/_info/help.txt", "r")
    help_txt = help_txt.readlines()
    if mode == 0:
        pass
    elif mode == 1:
        help_txt = help_txt[10:31]
    elif mode == 2:
        help_txt = help_txt[32:43]
    elif mode == 3:
        help_txt = help_txt[44:47]
    elif mode == 4:
        help_txt = help_txt[48:]

    for txt in help_txt:
        typer.echo(txt.replace('\n', ''))

#Status
@app.command()
def status():
    subprocess.run(args=[sys.executable, "./_important/status.py"])

#Clear
@app.command()
def clear_terminal():
    if sys.platform == "win32":
        os.system('cls')
    else:
        os.system('clear')

### Mount Functions
#Mount Status
@app.command()
def mount():
    subprocess.run(args=[sys.executable, "./_important/mount.py"])

#Mount Go-to Equitorial
@app.command()
def goto_rd(ra, dec,mount_mode):
    answer = typer.prompt("Do you want to go to RA: "+ra+", DEC: "+dec+"? [y/n]")
    if mount_mode == "degree":
        RA = pyobs.degree2float(ra)
    elif mount_mode == "hour":
        RA = pyobs.hour2float(ra)
    DEC = pyobs.degree2float(dec)

    if answer == "y":
        subprocess.run(args=[sys.executable, f"./_important/goto_rd.py", "-a", f"{RA:.7f}", "-d", f"{DEC:.7f}"])
    else:
        typer.echo("Go-to rd function denied.")

#Mount Go-to Horizontal
@app.command()
def goto_aa(alt, az):
    answer = typer.prompt("Do you want to go to ALT: "+alt+", AZ: "+az+"? [y/n]")
    ALT = pyobs.degree2float(alt)
    AZ = pyobs.degree2float(az)
    if answer == "y":
        subprocess.run(args=[sys.executable, f"./_important/goto_aa.py", "-a", f"{ALT:.7f}", "-z", f"{AZ:.7f}"])
    else:
        typer.echo("Go-to aa function denied.")


#Sync Equitorial
@app.command()
def sync_rd(ra,dec,mount_mode):
    if mount_mode == "degree":
        RA = pyobs.degree2float(ra)
    elif mount_mode == "hour":
        RA = pyobs.hour2float(ra)
    DEC = pyobs.degree2float(dec)

    answer = typer.prompt("Do you want to sync to RA: "+ra+", DEC: "+dec+"? [y/n]")
    if answer == "y":
        subprocess.run(args=[sys.executable, f"./_important/sync_rd.py", "-a",f"{RA:.7f}", "-d", f"{DEC:.7f}"])
    else:
        typer.echo("Sync rd function denied.")

#Mount Controller
@app.command()
def mount_control(direction, amplitude, unit):
    subprocess.run(args=[sys.executable, f"./_important/goto_control.py", "-d",direction, "-a", f"{amplitude:.7f}", "-u", unit])

#Sync Horizontal
@app.command()
def sync_aa(alt, az):
    answer = typer.prompt("Do you want to sync to ALT: "+alt+", AZ: "+az+"? [y/n]")
    ALT = pyobs.degree2float(alt)
    AZ = pyobs.degree2float(az)
    if answer == "y":
        subprocess.run(args=[sys.executable, f"./_important/sync_aa.py", "-a", f"{ALT:.7f}","-z",f"{AZ:.7f}"])
    else:
        typer.echo("Sync aa function denied.")

#Tracking On/Off
@app.command()
def tracking(switch):
    PATH = os.path.dirname(__file__)
    if switch == "on":
        subprocess.run(args=[sys.executable, PATH+"/_important/tracking.py", "-t", "on"])
    elif switch == "off":
        subprocess.run(args=[sys.executable, PATH+"/_important/tracking.py", "-t", "off"])
    else:
        typer.echo("Wrong format. Please insert tracking [on/off].")

#Park
@app.command()
def park():
    subprocess.run(args=[sys.executable, f"./_important/parking.py","-p","park"])

#Unpark
@app.command()
def unpark():
    subprocess.run(args=[sys.executable, f"./_important/parking.py","-p","unpark"])

### Camera Functions
#Camera
@app.command()
def camera():
    subprocess.run(args=[sys.executable, f"./_important/camera.py"])

#Set Cooling
@app.command()
def set_cooling(T):
    subprocess.run(args=[sys.executable, f"./_important/set_cooler_temp.py", "-t", f"{int(T)}"])

#Cooler
@app.command()
def cooler(switch):
    if switch == True:
        subprocess.run(args=[sys.executable, f"./_important/cooler.py","-s","on"])
    elif switch == False:
        subprocess.run(args=[sys.executable, f"./_important/cooler.py","-s","off"])

#Exposure
@app.command()
def exp(name, exptime, iter = 1, xbin = 1, ybin = 1):
    if exptime >= 60:
        pulseguide = subprocess.Popen(args=[sys.executable, f"./_important/pulseguide.py", "-t", f"{(exptime+2)*iter:.2f}"])
    subprocess.run(args=[sys.executable, f"./_important/exposure.py", "-n", name, "-t", f"{exptime:.2f}", "-i", f"{int(iter)}","-x",f"{xbin:1d}", "-y", f"{ybin:1d}"])

    if exptime >= 60:
        pulseguide.kill()
#Flat
@app.command()
def flat(name, exptime, iter = 1, xbin = 1, ybin = 1):
    subprocess.run(args=[sys.executable, f"./_important/flat.py", "-n", name, "-t", f"{exptime:.2f}", "-i", f"{int(iter)}","-x",f"{xbin:1d}", "-y", f"{ybin:1d}"])

#Dark
@app.command()
def dark(name, exptime, iter = 1, xbin = 1, ybin = 1):
    subprocess.run(args=[sys.executable, f"./_important/dark.py", "-n", name, "-t", f"{exptime:.2f}", "-i", f"{int(iter)}","-x",f"{xbin:1d}", "-y", f"{ybin:1d}"])

#Bias
@app.command()
def bias(name, iter = 1, xbin = 1, ybin = 1):
    subprocess.run(args=[sys.executable, f"./_important/bias.py", "-n", name, "-i", f"{int(iter)}","-x",f"{xbin:1d}", "-y", f"{ybin:1d}"])

### Focuser Functions
#Focus
@app.command()
def focus(dx):
    subprocess.run(args=[sys.executable, f"./_important/focus.py","-f",f"{int(dx)}"])
    
#Auto Focus
@app.command()
def auto_focus(start, interval, iteration, exptime, name):
    exptime = float(exptime)
    subprocess.run(args=[sys.executable,f"./_important/focus.py","-f",f"{int(start)}"])
    sleep(5)
    for i in range(int(iteration)):
        xbin = 1
        ybin = 1
        typer.echo(f"Exposing Image {i+1}")
        subprocess.run(args=[sys.executable,f"./_important/focus.py","-f",f"{int(interval)}"])
        sleep(3)
        subprocess.run(args=[sys.executable, f"./_important/exposure.py", "-n", "./focus/"+name+f"_{int(interval)*(i+1)}", "-t", f"{exptime:.2f}", "-i", f"{1}","-x","1", "-y", "1"])
    
    focus_q = typer.prompt("Do you wnat to find best focal position?[y/n]")
    if focus_q == "y":
        subprocess.run(args=[sys.executable,f"./_important/find_focus.py"])

# only find focus
@app.command()
def find_focus():
    subprocess.run(args=[sys.executable,f"./_important/find_focus.py"])

# Switch
@app.command()
def switch(onoff):
    if onoff:
        subprocess.run(args=[sys.executable,f"./_important/switch.py", "-s","on"])
    else:
        subprocess.run(args=[sys.executable,f"./_important/switch.py", "-s","off"])

@app.command()
def switch_status():
    subprocess.run(args=[sys.executable,f"./_important/switch_status.py"])

### Extra Functions
@app.command()
def query(img):
    subprocess.run(args=[sys.executable, f"./_important/query.py","-i",img])

#Main function
def main():
    #Mount mode
    mount_mode = "hour"

    #Binning
    xbinning = 1
    ybinning = 1

    #Path
    savepath = "C:\\RASA_Data\\"
    infopath = "./"
    
    #Clear Terminal
    clear_terminal()

    #Initial function
    observer = log_in()

    observer_txt = open(infopath+"/_important/_info/observer.txt", 'w')
    observer_txt.write(observer)
    observer_txt.close()


    while True:
        command = typer.prompt("\n")
        
        ### Main function
        #Help
        if command == "help":
            help(0)
        elif command == "help mount":
            help(1)
        elif command == "help camera":
            help(2)
        elif command == "help focuser":
            help(3)
        elif command == "help extra":
            help(4)
        
        #Status
        elif command == "status":
            status()
            switch_status()
            typer.echo("[Save Path]: "+savepath)

        #Clear Terminal
        elif command == "clear":
            clear_terminal()
        
        #Save path
        elif command == "path":
            typer.echo("[Save Path]: "+savepath)
            savepath = typer.prompt("Enter the new save path")
        
        #Quit Program
        elif command == "quit":
            typer.Exit()
            break
        
        ### Mount function
        #mount info
        elif command == "mount":
            mount()
            typer.echo("[Mode]: "+mount_mode)

        #mount setting
        elif "mount mode" in command:
            command = command.split(" ")
            if command[2] == "hour":
                mount_mode = "hour"
            elif command[2] == "degree":
                mount_mode = "degree"

        #goto rd
        elif "goto rd" in command:
            if len(command) == 7:
                ra = typer.prompt("RA ")
                dec = typer.prompt("DEC ")
            else:
                command = command.split(" ")
                if len(command) == 4:
                    ra = command[2]
                    dec = command[3]
            
            try:
                goto_rd(ra, dec,mount_mode)
            except Exception as E:
                typer.echo("[Error]: "+E)
        
        #goto aa
        elif "goto aa" in command:
            if len(command) == 7:
                alt = typer.prompt("ALT ")
                az = typer.prompt("AZ ")
                goto_aa(alt, az)
            else:
                command = command.split(" ")
                if len(command) == 4:
                    alt = command[2]
                    az = command[3]
                    goto_aa(alt,az)
                else:
                    typer.echo("Wrong format. Please insert goto aa [ALT] [AZ].")

        #sync rd
        elif "sync rd" in command:
            if len(command) == 7:
                ra = typer.prompt("RA ")
                dec = typer.prompt("DEC ")
                sync_rd(ra, dec,mount_mode)
            else:
                command = command.split(" ")
                if len(command) == 4:
                    ra = command[2]
                    dec = command[3]
                    sync_rd(ra,dec,mount_mode)
                else:
                    typer.echo("Wrong format. Please insert sync ra [RA] [DEC].")
        
        #sync aa
        elif "sync aa" in command:
            if len(command) == 7:
                alt = typer.prompt("ALT ")
                az = typer.prompt("AZ ")
                sync_aa(alt, az)
            else:
                command = command.split(" ")
                if len(command) == 4:
                    alt = command[2]
                    az = command[3]
                    sync_aa(alt,az)
                else:
                    typer.echo("Wrong format. Please insert sync aa [ALT/AZ].")

        #Tracking on/off
        elif "tracking" in command:
            try:
                command = command.split(" ")
                tracking(command[1])
            except:
                typer.echo("Wrong format.")

        #Simple Controll
        elif command[:2] == "ra":
            command = command.split(" ")
            if len(command) == 3:
                direction = "ra"
                unit = command[2]
                amp = float(command[1])
                mount_control(direction=direction, amplitude=amp, unit = unit)
            else:
                typer.echo("Wrong format. Please intert [Direction] [Amplitude] [Unit]")

        elif command[:3] == "dec":
            command = command.split(" ")
            if len(command) == 3:
                direction = "dec"
                unit = command[2]
                amp = float(command[1])
                mount_control(direction=direction, amplitude=amp, unit = unit)
            else:
                typer.echo("Wrong format. Please intert [Direction] [Amplitude] [Unit]")


        elif command[:3] == "alt":
            command = command.split(" ")
            if len(command) == 3:
                direction = "alt"
                unit = command[2]
                amp = float(command[1])
                mount_control(direction=direction, amplitude=amp, unit = unit)
            else:
                typer.echo("Wrong format. Please intert [Direction] [Amplitude] [Unit]")


        elif command[:2] == "az":
            command = command.split(" ")
            if len(command) == 3:
                direction = "az"
                unit = command[2]
                amp = float(command[1])
                mount_control(direction=direction, amplitude=amp, unit = unit)
            else:
                typer.echo("Wrong format. Please intert [Direction] [Amplitude] [Unit]")
        
        #Park
        elif command == "park":
            typer.echo("Park Telescope.")
            park()
        #Unpark
        elif command == "unpark":
            typer.echo("Unpark Telescope.")
            unpark()

        ### Camera function
        #Camera Status
        elif command == "camera":
            camera()

        #Set Cooler Temperature
        elif "set cooler" in command:
            try:

                command = command.split(" ")
                set_cooling(float(command[2]))
            except:
                typer.echo("Wrong format.")

        #Cooler
        elif command == "cooler on":
            cooler(True)
        elif command == "cooler off":
            cooler(False)

        #Exposure
        elif "exposure" in command:
            command = command.split(" ")
            if True:
                if len(command) == 1:
                    name = savepath + typer.prompt("Name")
                    name.replace(" ", "_")
                    exptime = typer.prompt("Exposure time[s]")
                    exptime = float(exptime)
                    iter = typer.prompt("Iterations")
                    iter = int(iter)
                    exp(name, exptime, iter, xbin=xbinning, ybin=ybinning)
                elif len(command) == 4:
                    exp(savepath + command[1], float(command[2]), int(command[3]), xbin=xbinning, ybin=ybinning)
            # except:
            #     typer.echo("Wrong format.")

        #Sequence
        elif command == "sequence":
            name = savepath + typer.prompt("Name")
            exptime_start = float(typer.prompt("Start exptime"))
            exptime_gap = float(typer.prompt("Interval of exptime"))
            exptime_num = int(typer.prompt("Number of exptime"))

            for i in range(exptime_num):
                exptime = exptime_start + exptime_gap*i
                exp(name+f"_{exptime:.3f}".replace(".",""), exptime, 1, xbin=xbinning, ybin=ybinning)


        #Robotic Observation
        elif "robotic obs" in command:
            command = command.split(" ")
            plan = pd.read_csv("plan.csv")
            expect_time = 0
            for i in range(len(plan)):
                expect_time += 1
                expect_time += (float(plan.loc[i]["exptime[s]"])+2)* int(plan.loc[i]["iteration[int]"])/60
                
            typer.echo(f"Expected time for robotic observation is about {expect_time:.1f} miunute.")
            answer = typer.prompt("Do you want to start robotic observation?[y/n]")
            for i in range(len(plan)):
                name = f"target_{i+1:3d}"
                ra = plan.loc[i]["ra[HH:MM:SS.SS]"]
                dec = plan.loc[i]["dec[DD:MM:SS.SS]"]
                exptime = float(plan.loc[i]["exptime[s]"])
                iter = int(plan.loc[i]["iteration[int]"])
                typer.echo(f"Move to target {i+1}. RA: "+ra+" DEC: "+dec)
                if mount_mode == "degree":
                    RA = pyobs.degree2float(ra)
                elif mount_mode == "hour":
                    RA = pyobs.hour2float(ra)
                DEC = pyobs.degree2float(dec)

                subprocess.run(args=[sys.executable, f"./_important/goto_rd.py", "-a", f"{RA:.7f}", "-d", f"{DEC:.7f}"])

                sleep(15)
                typer.echo(f"Start exposure on target {i+1}. Exptime: {exptime:3f} Repeat: {iter}")
                exp(name, exptime, iter = iter, xbin=xbinning, ybin=ybinning)

        #Sky Scanning
        elif "sky scan" == command:
            plan_file = typer.prompt("Plan file name:")
            plan = pd.read_csv(plan_file)
            exptime = typer.prompt("Exposure time[s]")
            exptime = float(exptime)
            iter = typer.prompt("Iterations")
            iter = int(iter)
            for i in range(len(plan)):
                ALT = plan.loc[i]["alt"]
                AZ = plan.loc[i]["az"]

                subprocess.run(args=[sys.executable, f"./_important/goto_aa.py", "-a", f"{ALT:.7f}", "-z", f"{AZ:.7f}"])
                sleep(15)
                tracking("on")
                sleep(30)
                
                #pulseguide = subprocess.Popen(args=[sys.executable, f"./_important/pulseguide.py", "-t", f"{(exptime+2)*iter:.2f}"])
                exp(f"alt{round(ALT)}az{round(AZ)}", exptime, iter =iter, xbin = 1, ybin = 1)
                #pulseguide.kill()
               

        
        #Flat
        elif "flat" in command:
            command = command.split(" ")
            try:
                if len(command) == 1:
                    name = savepath + typer.prompt("Name")
                    name.replace(" ", "_")
                    exptime = typer.prompt("Exposure time[s]")
                    exptime = float(exptime)
                    iter = typer.prompt("Iterations")
                    iter = int(iter)
                    flat(name, exptime, iter = iter, xbin=xbinning, ybin=ybinning)
                elif len(command) == 4:
                    flat(command[1], float(command[2]), iter = int(command[3]), xbin=xbinning, ybin=ybinning)
            except:
                typer.echo("Wrong format.")

        #Dark
        elif command == "dark list":
            dark_list = open("./_important/_info/dark_list.txt", "r")
            dark_exptimes = []
            dark_exptimes_txt = ""
            for line in dark_list.readlines():
                if "Dark List" in line:
                    continue
                else:
                    dark_exptimes.append(float(line.replace("\n", "")))
                    dark_exptimes_txt += line.replace("\n", "")+" "

            print("Current dark exposure list: "+dark_exptimes_txt)
            dark_list.close()

        elif command == "clear dark list":
            dark_list = open("./_important/_info/dark_list.txt", "w")
            dark_list.write("Dark List\n")
            dark_list.close()

        elif "dark sequence" == command:
            dark_list = open("./_important/_info/dark_list.txt", "r")
            dark_exptimes = []
            for line in dark_list.readlines():
                if "Dark List" in line:
                    continue
                else:
                    dark_exptimes.append(float(line.replace("\n", "")))

            bias("bias", iter = 9, xbin=xbinning, ybin=ybinning)
            for exptime in dark_exptimes:
                dark(f'dark{round(exptime):03d}', exptime, iter = 9, xbin=xbinning, ybin=ybinning)

        elif "dark" in command:
            command = command.split(" ")
            try:
                if len(command) == 1:
                    name = savepath + typer.prompt("Name")
                    name.replace(" ", "_")
                    exptime = typer.prompt("Exposure time[s]")
                    exptime = float(exptime)
                    iter = typer.prompt("Iterations")
                    iter = int(iter)
                    dark(name, exptime, iter=iter, xbin=xbinning, ybin=ybinning)
                elif len(command) == 4:
                    dark(command[1], float(command[2]), iter=int(command[3]), xbin=xbinning, ybin=ybinning)
            except:
                typer.echo("Wrong format.")

        #Bias
        elif "bias" in command:
            command = command.split(" ")
            try:
                if len(command) == 1:
                    name = savepath + typer.prompt("Name")
                    name.replace(" ", "_")
                    iter = typer.prompt("Iterations")
                    iter = int(iter)
                    bias(name, iter = iter, xbin=xbinning, ybin=ybinning)
                elif len(command) == 3:
                    bias(command[1], iter = int(command[3]), xbin=xbinning, ybin=ybinning)
            except:
                typer.echo("Wrong format.")

        #Binning Setting
        elif command == "binning":
            typer.echo(f"X binning: {xbinning:1d}")
            typer.echo(f"Y binning: {ybinning:1d}")
            try:
                xbinning = int(typer.prompt("Insert X binning"))
                ybinning = int(typer.prompt("Insert Y binning"))
            except:
                typer.echo("Enter the integer number.")
                xbinning, ybinning = 1, 1

        ### Focuser function
        elif command == "focus":
            focus(0)
            
        elif command == "focus auto":
            answer = typer.prompt("Do you want to clear the focusing image?[y/n]")
            if answer == "y":
                focus_files = os.listdir('./focus')
                for filename in focus_files:
                    os.remove('./focus/'+filename)
                
            select_obj = typer.prompt("Do you want to check the proper open cluster?[y/n]")
            if select_obj == 'y':
                subprocess.run(args=[sys.executable, f"./_important/focus_obj.py"])

            start = typer.prompt("Start Point")
            interval = typer.prompt("Interval")
            iteration = typer.prompt("Iteration")
            exptime = typer.prompt("Exptime[s]")
            name = typer.prompt("File name")
            auto_focus(start, interval, iteration, exptime, name)

        elif command == "find focus":
            find_focus()

        elif "focus" in command:
            command = command.split(" ")
            if len(command) == 1:
                dx = typer.prompt("How long do you want to change?")
            elif len(command) == 2:
                dx = command[1]
                
            try:
                focus(int(dx))
            except:
                typer.echo("Wrong format.")
        
        ### Switch function
        elif "switch" in command:
            if command == "switch on":
                switch(True)
            elif command == "switch off":
                switch(False)

        ### Extra function
        elif "query" in command:
            if command == "query prev":
                if True:
                    prev_img = open("./_important/_info/prev_img.txt", "r")
                    prev_img_name =  prev_img.readlines()[0]
                    prev_img.close()
                    print("Do query with image "+prev_img_name)
                    query(prev_img_name)
                # except Exception as e:
                #     print(e)
                   
            else:
                try:
                    command = command.split(" ")
                    if len(command) == 1:
                        img = typer.prompt("Image location")
                    elif len(command) == 2:
                        img = command[1]
                    query(img)
                except:
                    typer.echo("Wrong format.")

        #Unexpected Command
        else:
            typer.echo(f"Unexpected command: {command}")

if __name__ == "__main__":
    main()
