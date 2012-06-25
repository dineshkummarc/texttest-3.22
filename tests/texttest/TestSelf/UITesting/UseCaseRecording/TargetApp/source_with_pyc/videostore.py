#!/usr/bin/env python
# Test GUI for 'PyUseCase'

import gtk, gobject, time, sys

class VideoStore:
    def __init__(self):
        self.model = gtk.ListStore(gobject.TYPE_STRING)
    def createTopWindow(self):
        # Create toplevel window to show it all.
        win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        win.set_title("The Video Store")
        win.connect("delete_event", self.quit)
        vbox = self.createWindowContents()
        win.add(vbox)
        win.show()
        win.resize(self.getWindowWidth(), self.getWindowHeight())
        return win
    def createWindowContents(self):
        vbox = gtk.VBox()
        vbox.pack_start(self.getTaskBar(), expand=False, fill=False)
        vbox.pack_start(self.getVideoView(), expand=True, fill=True)
        vbox.show()
        return vbox
    def getTaskBar(self):
        taskBar = gtk.HBox()
        label = gtk.Label("New Movie Name  ")
        nameEntry = gtk.Entry()
        button = gtk.Button()
        button.set_label("Add")
        button.connect("clicked", self.addMovie, nameEntry)
        taskBar.pack_start(label, expand=False, fill=True)
        taskBar.pack_start(nameEntry, expand=True, fill=True)
        taskBar.pack_start(button, expand=False, fill=False)
        label.show()
        nameEntry.show()
        button.show()
        taskBar.show()
        return taskBar
    def getVideoView(self):
        view = gtk.TreeView(self.model)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Movie Name", renderer, text=0)
        view.append_column(column)
        view.expand_all()
        view.show()

        # Create scrollbars around the view.
        scrolled = gtk.ScrolledWindow()
        scrolled.add(view)
        scrolled.show()    
        return scrolled
    def getWindowHeight(self):
        return (gtk.gdk.screen_height() * 2) / 5
    def getWindowWidth(self):
        return (gtk.gdk.screen_width()) / 5
    def run(self):
        try:
            topWindow = self.createTopWindow()
            gtk.main()
        except KeyboardInterrupt:
            pass
    def addMovie(self, button, entry, *args):
        movieName = entry.get_text()
        self.model.append([ movieName ])
        print "Adding movie '" + movieName + "'. There are now", self.model.iter_n_children(None), "movies."
    def quit(self, *args):
        print "Exiting the video store!"
        gtk.main_quit()
        
if __name__ == "__main__":
    # Just to make it fail (make record and replay different...)
    import os
    print "Started the video store. The process ID is", os.getpid()
    if os.getenv("SABOTAGE_VIDEOSTORE"):
        print "Sabotage!"
    else:
        sys.stdout.flush()
        program = VideoStore()
        program.run()
