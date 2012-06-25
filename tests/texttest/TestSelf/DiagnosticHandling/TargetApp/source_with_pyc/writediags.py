#!/usr/bin/env python
import os, log4py, time

time.sleep(int(os.getenv("SLEEP_TIME", "0")))
print "This is a simple diagnostic-writing program"

# Point log4py at the configuration file to read
rootLogger = log4py.Logger(log4py.TRUE, os.getenv("TESTDIAG_READFILE"))

logger1 = log4py.Logger().get_instance("firstdiag")
logger1.info("Some information")
logger1.debug("Some debug stuff")

logger2 = log4py.Logger().get_instance("seconddiag")
logger2.info("Some information")
logger2.debug("Some debug stuff")

logger3 = log4py.Logger().get_instance("thirddiag")
logger3.info("Some information")
logger3.debug("Some debug stuff")
