
""" SWT utilities """
from org.eclipse import swt
from java.text import SimpleDateFormat
import storytext.guishared

def getRealUrl(browser):
    url = browser.getUrl()
    return url if url != "about:blank" else ""

def getTextLabel(widget):
    return storytext.guishared.getTextLabel(widget, "getChildren", swt.widgets.Label)

def getDateFormat(dateType):
    if dateType == swt.SWT.TIME:
        # Default format is locale-dependent, no reason to make tests fail in different locales
        return SimpleDateFormat("kk:mm:ss")
    else:
        # Seems to be default format for swt.SWT.DATE, should be locale-independent
        return SimpleDateFormat("M/d/yyyy") 

# For some reason StackLayout does not affect visible properties, so things that are hidden get marked as visible
# Workaround these things
def getTopControl(widget):
    if hasattr(widget, "getLayout"):
        layout = widget.getLayout()
        if hasattr(layout, "topControl"):
            return layout.topControl

def isVisible(widget):
    if not hasattr(widget, "getVisible"):
        return True
    if not widget.getVisible():
        return False

    parent = widget.getParent()
    if not parent:
        return True
    topControl = getTopControl(parent)
    if topControl and topControl is not widget:
        return False
    else:
        return isVisible(parent)

