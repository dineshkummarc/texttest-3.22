#!/usr/bin/env python

import os

def doDir(dir, remove=0):
    for file in os.listdir(dir):
        fullPath = os.path.join(dir, file)
        datadirs = [ "TargetApp", "texttesttmp" ]
        tryRemove = file != "CVS" and (remove or file in datadirs)
        if tryRemove:
            os.system("chmod -w " + fullPath)            
        if os.path.isdir(fullPath):
            doDir(fullPath, tryRemove)

doDir(os.getcwd())
