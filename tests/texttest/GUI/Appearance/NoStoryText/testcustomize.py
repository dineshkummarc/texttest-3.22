
import __builtin__, sys

origImport = __builtin__.__import__
def myImport(name, globals=None, *args, **kwargs):
    # Only do this within TextTest - don't screw up StoryText itself!
    if name in [ "storytext" ] and globals and "plugins" in globals:
        raise ImportError, "No module named storytext"
    else:
        return origImport(name, globals, *args, **kwargs)

__builtin__.__import__ = myImport
