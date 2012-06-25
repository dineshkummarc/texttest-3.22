
import os, time, sys

orig_listdir = os.listdir

def slow_listdir(dirname, *args, **kwargs):
    basename = os.path.basename(dirname)
    if basename == "Basic2":
        time.sleep(3)
    return orig_listdir(dirname, *args, **kwargs)

os.listdir = slow_listdir
