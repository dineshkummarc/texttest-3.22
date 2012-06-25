#!/usr/bin/env python

import os
os.mkdir("readonlydir")
file = open("readonlydir/readonlyfile", "w")
file.write("dummy")
file.close()
os.chmod("readonlydir/readonlyfile", 0500)
os.chmod("readonlydir", 0500)
print 'Hello World!'
