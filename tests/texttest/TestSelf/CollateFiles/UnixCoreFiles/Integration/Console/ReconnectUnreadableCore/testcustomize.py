
import shutil, os

origcopyfile = shutil.copyfile

def copyfile(src, dst):
    if os.path.basename(src) == "core":
        raise OSError, "Permission denied!"
    else:
        origcopyfile(src, dst)

shutil.copyfile = copyfile
