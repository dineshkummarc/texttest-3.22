
import os

origIsFile = os.path.isfile

def is_file(path):
    fname = os.path.basename(path)
    if fname in [ "output.hello", "output.hellocmp" ] and path.find("TargetApp") == -1:
        return False
    return origIsFile(path)

os.path.isfile = is_file
