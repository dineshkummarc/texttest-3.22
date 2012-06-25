
import shutil

orig_copyfile = shutil.copyfile

def copyfile(src, dst):
    if dst.endswith("_therun"):
        raise IOError, "Can't write there!"
    else:
        orig_copyfile(src, dst)

shutil.copyfile = copyfile
