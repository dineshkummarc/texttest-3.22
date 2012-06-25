#!/usr/bin/env python

import shutil, sys, socket

shutil.copyfile(sys.argv[1], sys.argv[2])

f= open(sys.argv[2], "a")
f.write("On machine " + socket.gethostname() + "\n")
f.close()
