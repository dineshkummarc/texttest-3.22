
import os

filePath = os.path.join(os.getenv("TEXTTEST_SANDBOX_ROOT"), "file")

if os.path.isfile(filePath):
    print "There is a file!"
else:
    open(filePath, "w").close()
    print "There was no file"

