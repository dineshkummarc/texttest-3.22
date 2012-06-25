
import subprocess
from time import sleep

RealPopen = subprocess.Popen
class SlowPopen(RealPopen):
    def __init__(self, cmdArgs, *args, **kwargs):
        RealPopen.__init__(self, cmdArgs, *args, **kwargs)
        if cmdArgs[0] == "qsub" or cmdArgs[0] == "bsub":
            SlowPopen.doneSleep = True
            print "Waiting Q thread for 5 seconds"
            sleep(5)
        
subprocess.Popen = SlowPopen
