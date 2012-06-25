#!/usr/bin/env python

import sys, time
toWrite = "cpu time: 2.5 seconds\n"
file = open("myfile", "w")
file.write(toWrite)
time.sleep(0.5) # Fix the windows race conditions...
