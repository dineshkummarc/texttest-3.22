#!/usr/bin/env python

import os, time

# Should get the test environment here, we might need it...
# If we don't, fake "crashing"
if os.getenv("MY_DIFF_PROGRAM"):
    time.sleep(1000)
