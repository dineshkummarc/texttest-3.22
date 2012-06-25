
import gtk, logging

class MyClipboard:
    def __init__(self, selection="CLIPBOARD"):
        self.selection = selection
        
    def set_text(self, text):
        logging.getLogger("gui log").info("Set " + self.selection + " text to " + repr(text))


def clipboard_get(*args):
    return MyClipboard(*args)

gtk.clipboard_get = clipboard_get
