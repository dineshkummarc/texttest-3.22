
import default

def getConfig(optionMap):
    return Config(optionMap)

class Config(default.Config):
    def getTestRunner(self):
        return MyTestRunner()

class MyTestRunner(default.RunTest):
    def __call__(self, test):
        if test.name.find("simple") != -1:
            raise Exception, "Don't do simple tests!"
        else:
            default.RunTest.__call__(self, test)

