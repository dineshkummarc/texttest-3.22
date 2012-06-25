#!/usr/bin/env python

import os
print 'Hello World!'
# Should be able to collate this
file = open("local", "w")
file.write("local\n")
file.close()

# Should get this without configuration
file = open("extra.hello", "w")
file.write("extra\n")
file.close()
