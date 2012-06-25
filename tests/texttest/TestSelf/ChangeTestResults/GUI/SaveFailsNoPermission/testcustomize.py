
import os

origRemove = os.remove
def myremove(file):
    if file.startswith(os.getenv("TEXTTEST_HOME")):
        raise OSError, "Permission denied: '" + file + "'"
    else:
        origRemove(file)
        
os.remove = myremove
