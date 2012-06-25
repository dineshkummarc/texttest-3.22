
import storytext.guishared, gtk

class WidgetAdapter(storytext.guishared.WidgetAdapter):
    def getChildWidgets(self):
        if hasattr(self.widget, "get_children"):
            return self.widget.get_children()
        else:
            return []
        
    def getWidgetTitle(self):
        return self.widget.get_title()

    def getLabel(self):
        text = self.getLabelText()
        if text and "\n" in text:
            return text.splitlines()[0] + "..."
        else:
            return text

    def getLabelText(self):
        if isinstance(self.widget, gtk.MenuItem):
            child = self.widget.get_child()
            # "child" is normally a gtk.AccelLabel, but in theory it could be anything
            if isinstance(child, gtk.Label):
                return child.get_text()
        elif hasattr(self.widget, "get_label"):
            return self.widget.get_label()

    def isAutoGenerated(self, name):
        return name.startswith("Gtk")

    def getName(self):
        return self.widget.get_name()
     

storytext.guishared.WidgetAdapter.adapterClass = WidgetAdapter
