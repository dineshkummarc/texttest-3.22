#!/usr/bin/env python

import os

if os.path.isfile("my_personal_file"):
    print "Found and read my file:", open("my_personal_file").read()

envVar = os.getenv("MY_ENV_VAR")
if envVar is not None:
    print "Got environment variable", envVar
