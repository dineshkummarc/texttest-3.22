
import gtk, os

origWindow = gtk.Window

def pixbuf_broken(icon):
    raise Exception, "Didn't like the look of image '" + os.path.basename(icon) + "'"

class Window(origWindow):
    def set_icon_from_file(self, filename):
        return pixbuf_broken(filename)

gtk.gdk.pixbuf_new_from_file = pixbuf_broken
gtk.Window = Window
