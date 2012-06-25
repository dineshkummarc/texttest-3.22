#!/usr/bin/env python

import os, time
try:
    time.sleep(int(os.getenv("TO_SLEEP", "0")))
    print 'Hello World!'
except KeyboardInterrupt:
    pass
