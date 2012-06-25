#!/usr/bin/env python
import os, time
time.sleep(int(os.getenv("SLEEP_TIME", "0")))
extraLine = os.getenv("EXTRA_LINE")
if extraLine:
    print extraLine
print 'Hello World!'
