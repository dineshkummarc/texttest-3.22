#!/usr/bin/env python

import os

if os.name == "posix":
  os.system("fake_executable.py 2> /dev/null")
else:
  os.system("fake_executable.py 2> nul")
