
import shutil

def rmtree(dir):
    raise OSError, "Permission denied removing " + dir

shutil.rmtree = rmtree
