
import subprocess, sys
from time import sleep

RealPopen = subprocess.Popen
class SlowPopen(RealPopen):
    doneSleep = False
    def __init__(self, cmdArgs, *args, **kwargs):
        RealPopen.__init__(self, cmdArgs, *args, **kwargs)
        if not self.doneSleep and (cmdArgs[0] == "qsub" or cmdArgs[0] == "bsub"):
            SlowPopen.doneSleep = True
            print "Waiting Q thread for 5 seconds"
            sys.stdout.flush()
            sleep(5)
        
subprocess.Popen = SlowPopen
