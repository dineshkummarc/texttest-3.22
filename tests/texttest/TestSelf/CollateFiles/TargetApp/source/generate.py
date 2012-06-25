#!/usr/bin/env python

import os, sys

def generateFile(name):
    print "Generating",name
    print >>file(name, "w"), name + "\nToday is Sunday"

generateFile("generated.first.dump")
generateFile("generated.second.dump")
generateFile("generated.third.dump")
if len(sys.argv) == 1:
    generateFile("created_1.dump")
    generateFile("created_2.dump")
