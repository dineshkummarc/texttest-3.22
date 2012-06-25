#!/usr/bin/env python

import os, sys
testdata = os.path.join(os.path.dirname(sys.argv[0]), "testdata")
if os.path.isfile(testdata):
    print 'Hello ' + open(testdata).read().strip() + "!"
else:
    print 'Hello World!'
