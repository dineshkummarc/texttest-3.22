#!/usr/bin/env python

import os, time
time.sleep(int(os.getenv("SLEEP_LENGTH", "0")))
print 'Hello All!'
