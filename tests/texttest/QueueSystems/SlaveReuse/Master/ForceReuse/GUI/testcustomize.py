
# In order to force reuse, we need to make sure we actually read all the tests before any of them start completing. Introduce a delay before first submission therefore.

import subprocess, sys
from time import sleep

RealPopen = subprocess.Popen
class SlowPopen(RealPopen):
    doneSleep = False
    def __init__(self, cmdArgs, *args, **kwargs):
        if not self.doneSleep and (cmdArgs[0] == "qsub" or cmdArgs[0] == "bsub"):
            SlowPopen.doneSleep = True
            print "Waiting Q thread for 1 second"
            sys.stdout.flush()
            sleep(1)
        RealPopen.__init__(self, cmdArgs, *args, **kwargs)
        
subprocess.Popen = SlowPopen
