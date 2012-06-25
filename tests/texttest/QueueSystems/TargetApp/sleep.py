#!/usr/bin/env python

try:
    import sys, time

    def getSleepLength():
        if len(sys.argv) > 1:
            return int(sys.argv[1])
        else:
            return 5

    sleepLength = getSleepLength()
    print "Sleeping for", sleepLength, "seconds..."
    sys.stdout.flush()
    time.sleep(sleepLength)
    print "Done"
except KeyboardInterrupt:
    pass
