#!/usr/bin/env python

import os
if os.path.isfile("testdata"):
    print 'Hello ' + open("testdata").read().strip() + "!"
else:
    print 'Hello World!'
