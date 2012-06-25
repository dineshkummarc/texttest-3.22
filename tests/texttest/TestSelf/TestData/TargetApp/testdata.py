#!/usr/bin/env python

import os
from time import sleep

def editFiles(dir):
    if os.path.basename(dir) == "writehere":
        fileName = open(os.path.join(dir, "newfile"), "w")
        fileName.write("New file!\n")
        fileName.close()
    if os.path.basename(dir) == "writeandremovehere":
        fileName = open(os.path.join(dir, "newfile"), "w")
        fileName.write("New file!\n")
        fileName.close()
        # Make sure we don't get race conditions, particularly on Windows!
        sleep(1)
        os.remove(os.path.join(dir, "newfile"))
    for fileName in os.listdir(dir):
        fullPath = os.path.join(dir, fileName)
        if fileName == "toRemove":
            os.remove(fullPath)
        elif fileName == "toEdit":
            file = open(fullPath, "a")
            file.write("Added stuff!\n")
            file.close()
        if os.path.isdir(fullPath):
            editFiles(fullPath)

file = open("readonlyfile")
print "Found and read my read-only file: ", file.read()
if os.path.isfile("readonlyfile2"):
    file = open("readonlyfile2")
    print "Found and read my second read-only file: ", file.read()

envVar = os.getenv("MY_ENV_VAR")
if envVar is not None:
    print "Got environment variable", envVar

writedirs = os.getenv("WRITEABLE_DIRS") 
if writedirs and os.path.isdir(writedirs):
    editFiles(writedirs)
else:
    print "Didn't get given a directory structure to edit!"
