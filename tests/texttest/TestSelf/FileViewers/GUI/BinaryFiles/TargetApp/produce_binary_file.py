#!/usr/bin/env python

fileName = "binary_output.hello"

print "The output to stdout is just plain text ...\n" + \
      "... but the output in '" + fileName + "' is not."

binaryFile = open(fileName, "wb");
for i in xrange(0, 155, 1):
    binaryFile.write(chr(i))
binaryFile.close()
