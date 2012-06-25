
import default, os

def getConfig(*args):
    return Config(*args)

class Config(default.Config):
    def extraReadFiles(self, test):
        files = {}
        if test.parent is None:
            files["Config"] = [ os.path.join(test.getDirectory(), "config.hello") ]
            files["Executable"] = [ os.path.join(test.getDirectory(), "hello.py") ]
        return files
