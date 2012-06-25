#!/usr/bin/env python

import subprocess, os

def devnull():
    if os.name == "posix":
        return "/dev/null"
    else:
        return "nul"

print 'Hello World, now sleeping!'
proc = subprocess.Popen([ "python", "-c", "import time; time.sleep(10)" ], stdin=open(devnull()), stdout=open(devnull(), "w"), stderr=subprocess.STDOUT)
print "Leaking sleep process : sleep process :", proc.pid
