#!/usr/bin/env python
# make it different
import os, shutil

print 'Hello World!'
ttHome = os.getenv("TEXTTEST_HOME")
origDir = os.path.join(ttHome, "orig")
newDir = os.path.join(ttHome, "new", "subdir")
#shutil.rmtree(origDir)
#os.rename(newDir, origDir)
