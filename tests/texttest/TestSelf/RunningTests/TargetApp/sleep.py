#!/usr/bin/env python

try:
    import os, sys, time

    print "Sleeping for 1000 seconds..."
    sys.stdout.flush()
    time.sleep(int(os.getenv("SLEEP_TIME", 1000))) # Until we get killed, basically
    print "Done"
except KeyboardInterrupt:
    # Don't print stack traces when killed, as Windows can't do this...
    pass
