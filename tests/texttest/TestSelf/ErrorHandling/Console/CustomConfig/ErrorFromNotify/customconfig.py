
import default, plugins

def getConfig(optionMap):
    return Config(optionMap)

class Config(default.Config):
    def getResponderClasses(self, *args):
        return default.Config.getResponderClasses(self, *args) + [ MyResponder ]

class MyResponder(plugins.Responder):
    def notifyLifecycleChange(self, *args):
        asfgagsdg
