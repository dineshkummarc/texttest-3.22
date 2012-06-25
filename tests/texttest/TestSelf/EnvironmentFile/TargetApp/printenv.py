#!/usr/bin/env python
import os, sys

def printEnv(name):
    if os.environ.has_key(name):
        print name, "=", os.environ[name]
    else:
        print name, " NOT DEFINED"

printEnv("VAR1")
printEnv("VAR2")
printEnv("EXTERNAL1")
if len(sys.argv) > 1:
    print "Got argument '" + sys.argv[1] + "'"
