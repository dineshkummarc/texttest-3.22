#!/usr/bin/env python
import sys

def get_input():
    if len(sys.argv) > 1:
        return open(sys.argv[1])
    else:
        return sys.stdin

print get_input().read()
print "An extra line from the second!"
