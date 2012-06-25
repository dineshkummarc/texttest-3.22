#!/usr/bin/env python
import os, time

print "Using display", os.getenv("DISPLAY")
time.sleep(int(os.getenv("TO_SLEEP", "0")))
