#!/usr/bin/env python

import os, subprocess, socket, sys

os.environ["PROXY_HOSTNAME"] = socket.gethostname()
os.environ["PROXY_ARG"] = sys.argv[1]
qsubCommandArgs = eval(os.getenv("TEXTTEST_SUBMIT_COMMAND_ARGS"))
subprocess.call(qsubCommandArgs)
