
import shutil, os

def rmtree(d):
    raise OSError, "[Errno 13] Permission denied: " + repr(d)

shutil.rmtree = rmtree

def chmod(d, *args):
    raise OSError, "[Errno 1] Operation not permitted."

os.chmod = chmod
