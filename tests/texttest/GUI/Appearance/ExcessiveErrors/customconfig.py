
import default, sys

def getConfig(optionMap):
    return Config(optionMap)

class Config(default.Config):
    def getTestRunner(self):
        return MyTestRunner()

class MyTestRunner(default.RunTest):
    def __call__(self, test):
        for i in range(2000):
            sys.stderr.write("Stupid error text!\n")
        default.RunTest.__call__(self, test)

