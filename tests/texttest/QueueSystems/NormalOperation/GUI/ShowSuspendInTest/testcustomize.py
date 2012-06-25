
import time

origSleep = time.sleep

# Just so the test doesn't go on forever...
def fakeSleep(seconds):
    newSleep = float(seconds) / 10
    origSleep(newSleep)

time.sleep = fakeSleep
