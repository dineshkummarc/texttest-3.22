
import __builtin__

origOpen = __builtin__.open

def myOpen(fileName, mode="r", *args, **kwargs):
    if ("w" in mode or "a" in mode) and "testsuite" in fileName:
        raise OSError, "Permission denied editing" + fileName
    else:
        return origOpen(fileName, mode, *args, **kwargs)

__builtin__.open = myOpen
