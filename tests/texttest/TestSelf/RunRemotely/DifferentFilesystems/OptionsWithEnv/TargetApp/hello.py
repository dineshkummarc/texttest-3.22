#!/usr/bin/env python

import os, sys

if os.path.isfile(sys.argv[1]):
    print 'Hello ' + open(sys.argv[1]).read().strip() + "!"
else:
    print 'Hello World!'
