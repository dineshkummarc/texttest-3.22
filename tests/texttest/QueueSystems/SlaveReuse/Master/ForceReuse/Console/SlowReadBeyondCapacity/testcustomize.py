
import os, time, sys

orig_listdir = os.listdir

def slow_listdir(dirname, *args, **kwargs):
    if dirname.find("Suite/Test") != -1:
        time.sleep(2)
    return orig_listdir(dirname, *args, **kwargs)

os.listdir = slow_listdir
