
# In order to force reuse, we need to make sure we actually read all the tests before any of them start completing. Introduce a delay before first submission therefore.

import subprocess, sys, os
from time import sleep

RealPopen = subprocess.Popen
real_listdir = os.listdir

doneSleep = False

class SlowPopen(RealPopen):
    def __init__(self, cmdArgs, *args, **kwargs):
        global doneSleep
        if not doneSleep and (cmdArgs[0] == "qsub" or cmdArgs[0] == "bsub"):
            doneSleep = True
            print "Waiting Q thread for 1 second"
            sys.stdout.flush()
            sleep(1)
        RealPopen.__init__(self, cmdArgs, *args, **kwargs)

def SlowListDir(path, *args):
    result = real_listdir(path, *args)
    global doneSleep    
    if not doneSleep and "framework_tmp" in result and "output.hello" in result:
        doneSleep = True
        print "Waiting a while..."
        sleep(2)
    return result
        
subprocess.Popen = SlowPopen
os.listdir = SlowListDir
