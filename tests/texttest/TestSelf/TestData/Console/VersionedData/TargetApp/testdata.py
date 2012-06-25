#!/usr/bin/env python

import os

readfile = os.getenv("READ_ONLY_FILE")
if readfile:
    print "Read file contains :\n" + open(readfile).read()
