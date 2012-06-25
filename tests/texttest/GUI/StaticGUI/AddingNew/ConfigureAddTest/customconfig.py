
from default.gtkgui import default_gui

# Graphical import test
class ImportTestCase(default_gui.ImportTestCase):
    def getEnvironment(self, *args):
        return { "MY_ENV_VAR" : "foo" }

class InteractiveActionConfig(default_gui.InteractiveActionConfig):
    def getReplacements(self):
        rep = default_gui.InteractiveActionConfig.getReplacements(self)
        rep[default_gui.ImportTestCase] = ImportTestCase
        return rep
