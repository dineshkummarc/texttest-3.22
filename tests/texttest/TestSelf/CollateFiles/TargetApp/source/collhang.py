#!/usr/bin/env python

import time, sys
try:
    sys.stdout.write("We went into an infinite loop!\n")
    sys.stdout.flush()	
    time.sleep(1000)
except KeyboardInterrupt:
    pass
