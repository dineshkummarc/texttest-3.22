
import os

origMkdir = os.mkdir

def myMkDir(dirname, *args):
    if os.path.basename(dirname) == "readonly_dir":
        raise OSError, "Permission denied: '" + dirname + "'"
    else:
        return origMkdir(dirname, *args)

os.mkdir = myMkDir
