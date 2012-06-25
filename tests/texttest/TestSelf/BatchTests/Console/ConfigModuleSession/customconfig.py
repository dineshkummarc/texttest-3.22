
import default

def getConfig(optionMap):
    return Config(optionMap)

class Config(default.Config):
    def getBatchSession(self, app):
        return "self_test"
