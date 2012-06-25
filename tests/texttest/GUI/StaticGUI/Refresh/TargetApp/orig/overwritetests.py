#!/usr/bin/env python

import os, shutil

print 'Hello World!'
ttHome = os.getenv("TEXTTEST_HOME")
origDir = os.path.join(ttHome, "orig")
newDir = os.path.join(ttHome, "new", "subdir")
shutil.rmtree(origDir)
os.rename(newDir, origDir)
for root, dirs, files in os.walk(origDir):
    for file in files:
        fullPath = os.path.join(root, file)
        os.utime(fullPath, None) # touch everything
