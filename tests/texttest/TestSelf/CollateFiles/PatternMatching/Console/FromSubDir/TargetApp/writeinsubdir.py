#!/usr/bin/env python

import os
os.mkdir("somedir")
for i in range(3):
    fileName = "somedir/writefile" + str(i+1) + ".dump"
    file = open(fileName, "w")
    file.write("Some info\n")
    file.close()
