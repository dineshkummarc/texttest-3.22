#!/usr/bin/env python
import os

readFile = os.getenv("TESTDIAG_READFILE")
print "Reading config file at", readFile
print "Contents:"
if readFile and os.path.isfile(readFile):
    print open(readFile).read()
    
