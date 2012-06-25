#!/usr/bin/env python

import os

print "Going to dump a core!"
# Produce fake core
file = open("core", "w")
file.write("Dummy core\n")
file.close()
