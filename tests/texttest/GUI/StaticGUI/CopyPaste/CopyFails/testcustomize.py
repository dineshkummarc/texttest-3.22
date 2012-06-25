
import shutil

realcopytree = shutil.copytree

def copytree(src, dst):
    realcopytree(src, dst)
    raise OSError, "Permission denied copying " + src

shutil.copytree = copytree
