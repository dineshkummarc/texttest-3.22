#!/usr/bin/env python

import os, time
print 'Hello ' + os.getenv("DISPLAY")
time.sleep(int(os.getenv("SLEEP_TIME", "0")))
