
import gtk, gobject

origFileChooserWidget = gtk.FileChooserWidget

class FileChooserWidget(origFileChooserWidget):
    def add_shortcut_folder(self, *args, **kw):
        raise gobject.GError, "Not letting you!"

gtk.FileChooserWidget = FileChooserWidget
