
import os, time

orig_isfile = os.path.isfile

def slow_isfile(path, *args, **kwargs):
    if os.path.basename(path) == "sleep.py":
        time.sleep(3)
    return orig_isfile(path, *args, **kwargs)

os.path.isfile = slow_isfile
