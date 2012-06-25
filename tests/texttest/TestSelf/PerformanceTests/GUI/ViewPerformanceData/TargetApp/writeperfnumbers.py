#!/usr/bin/env python

import sys, time
toWrite = "cpu time: 2.5 seconds"
print toWrite
sys.stderr.write(toWrite + "\n")
time.sleep(0.5) # Fix the windows race conditions...
