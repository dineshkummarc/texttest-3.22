#!/usr/bin/env python

import os, socket, sys

print "Test on", socket.gethostname(), "with arg", sys.argv[1]
print "Proxy on", os.getenv("PROXY_HOSTNAME"), "with arg", os.getenv("PROXY_ARG")
