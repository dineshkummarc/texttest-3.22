#!/usr/bin/env python
print 'Hello World!'

import os

file = open(os.path.join(os.getenv("TEXTTEST_HOME"), "config.hello"), "a")
file.write("[run_dependent_text]\noutput:Hello\n")
file.close()
