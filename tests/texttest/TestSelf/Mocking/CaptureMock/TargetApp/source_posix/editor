#!/usr/bin/env python

import sys, os

def editFile(fileName):
    print "Editing file", fileName
    file = open(fileName, "a")
    file.write("The Editor has made its mark\n")

fileName = sys.argv[1]
if os.path.isfile(fileName):
    editFile(fileName)
else:
    editFile(fileName + "/subdir/file")
