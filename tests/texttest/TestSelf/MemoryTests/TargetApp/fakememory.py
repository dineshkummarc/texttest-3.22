#!/usr/bin/env python

def writeMemory(mem, unit="MB"):
    print "Memory usage now", mem, unit 

# Just print a bunch of numbers and an intro. Pretend to be writing memory numbers
print "Running Fake Memory Program..."
writeMemory(35.6)
writeMemory(47.2)
writeMemory(47.8)
writeMemory(42.3)
writeMemory(38.4)
print "Improving memory usage now!" # make sure we don't fall over here...
writeMemory(800.0, "kb")
