#!/usr/bin/env python

import os, signal
print "Die..."
os.kill(os.getpid(), signal.SIGTERM)
