#!/usr/bin/env python

import signal

# Slow it down a bit to avoid race conditions
def handler(*args):
    import time
    time.sleep(2)
    raise KeyboardInterrupt()

signal.signal(signal.SIGINT, handler)

try:
    import os, sys, time

    print "Sleeping for 1000 seconds..."
    sys.stdout.flush()
    time.sleep(1000) # Until we get killed, basically
    print "Done"
except KeyboardInterrupt:
    # Don't print stack traces when killed, as Windows can't do this...
    pass
