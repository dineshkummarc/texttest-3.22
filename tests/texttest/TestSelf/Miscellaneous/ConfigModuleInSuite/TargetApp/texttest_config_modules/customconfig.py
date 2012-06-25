import default

def getConfig(optionMap):
    return Config(optionMap)

class Config(default.Config):
    def getTestRunner(self):
        return MyTestRunner()

class MyTestRunner(default.RunTest):
    def __call__(self, test):
        print "Look, we wrote a custom config!"
        default.RunTest.__call__(self, test)
