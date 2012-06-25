
import os, time, sys

orig_listdir = os.listdir
orig_mkdir = os.mkdir
slept = False

def slow_mkdir(dirname, *args, **kwargs):
    basename = os.path.basename(dirname)
    if basename == "t1":
        time.sleep(3)
    return orig_mkdir(dirname, *args, **kwargs)

def slow_listdir(dirname, *args, **kwargs):
    basename = os.path.basename(dirname)
    global slept
    if basename == "t2" and not slept:
        time.sleep(2)
        slept = True
    return orig_listdir(dirname, *args, **kwargs)

os.listdir = slow_listdir
os.mkdir = slow_mkdir
