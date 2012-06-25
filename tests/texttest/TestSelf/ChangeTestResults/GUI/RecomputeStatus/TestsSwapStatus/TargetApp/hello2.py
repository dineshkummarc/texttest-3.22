#!/usr/bin/env python
import os
test = os.path.basename(os.getcwd())
print 'Hello', test
if test == "Test2":
    print "Extra"

