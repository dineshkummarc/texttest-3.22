
"""
Generic module broken out from guiplugins. Contains utility code that can be
called from anywhere in the gtkgui package
"""
import plugins, os, sys, operator, types, subprocess, locale
from copy import copy

# gtk.accelerator_valid appears utterly broken on Windows
def windowsAcceleratorValid(key, mod):
    name = gtk.accelerator_name(key, mod)
    return len(name) > 0 and name != "VoidSymbol"

try:
    import gtk
    if os.name == "nt":
        gtk.accelerator_valid = windowsAcceleratorValid
except ImportError:
    pass # We might want to document the config entries, silly to fail on lack of GTK...


guiConfig = None

class Utf8Converter:
    langVars = ('LC_ALL', 'LC_CTYPE', 'LANG', 'LANGUAGE')
    def __init__(self):
        self.encodings = self.getEncodings()

    def getEncodings(self):
        encodings = [ 'utf-8' ]
        localeEncoding = locale.getdefaultlocale()[1]
        if localeEncoding and not localeEncoding in encodings:
            encodings.insert(0, localeEncoding)
        return encodings
    
    def convert(self, text, extraEncodingLookup=None):
        unicodeInfo = self.decodeText(text, extraEncodingLookup)
        return unicodeInfo.encode('utf-8', 'replace')

    def getExtraEncodings(self, extraEncodingLookup):
        # Calling undocumented method to save copying it, best not to crash if it has been renamed.
        # Don't do this on Windows, the variables concerned don't apply there anyway
        if extraEncodingLookup and os.name != "nt" and hasattr(locale, "_parse_localename"):
            # Copied from locale.getdefaultlocale, would be nice if we could actually call this code
            for variable in self.langVars:
                localename = extraEncodingLookup(variable)
                if localename:
                    if variable == 'LANGUAGE':
                        localename = localename.split(':')[0]
                    extraEncoding = locale._parse_localename(localename)[1]
                    if extraEncoding and extraEncoding not in self.encodings and extraEncoding.lower() not in self.encodings:
                        return [ extraEncoding ]
        return []

    def decodeText(self, text, extraEncodingLookup):
        encodingsToTry = self.encodings + self.getExtraEncodings(extraEncodingLookup)
        for encoding in encodingsToTry:
            try:
                return unicode(text, encoding, errors="strict")
            except Exception:
                pass

        sys.stderr.write("WARNING: TextTest's textual display had some trouble with character encodings.\n" + \
                         "It tried the encoding(s) " + " and ".join(encodingsToTry) + \
                         ",\nbut the Unicode replacement character still had to be used.\n" + \
                         "Please ensure your locale is compatible with the encodings in your test files.\n" + \
                         "The problematic text follows:\n\n" + text.strip() + "\n")
        return unicode(text, encodingsToTry[0], errors="replace")

utf8Converter = Utf8Converter()

def convertToUtf8(*args): # gtk.TextViews insist we do the conversion ourselves
    return utf8Converter.convert(*args)


def openLinkInBrowser(target):
    if os.name == "nt" and not os.environ.has_key("BROWSER"):
        os.startfile(target)
        return 'Started "<default browser> ' + target + '" in background.'
    else:
        browser = os.getenv("BROWSER", "firefox")
        cmdArgs = [ browser, target ]
        subprocess.call(cmdArgs)
        return 'Started "' + " ".join(cmdArgs) + '" in background.'


class RefreshTips:
    def __init__(self, name, refreshCell, refreshColumn, refreshIndex):
        self.name = name
        self.refreshIndex = refreshIndex
        self.refreshColumn = refreshColumn
        self.refreshCell = refreshCell

    def hasRefreshIcon(self, view, path): # pragma: no cover - StoryText cannot test tooltips (future?)
        model = view.get_model()
        if isinstance(model, gtk.TreeModelFilter):
            childPath = model.convert_path_to_child_path(path)
            return model.get_model()[childPath][self.refreshIndex]
        else:
            return model[path][self.refreshIndex]

    def getTooltip(self, view, widget_x, widget_y, dummy, tooltip): # pragma: no cover - StoryText cannot test tooltips (future?)
        x, y = view.convert_widget_to_tree_coords(widget_x, widget_y)
        pathInfo = view.get_path_at_pos(x, y)
        if pathInfo is None:
            return False
        
        path, column, cell_x, _ = pathInfo
        if column is not self.refreshColumn or not self.hasRefreshIcon(view, path):
            return False

        cell_pos = column.cell_get_position(self.refreshCell)[0]
        if cell_x > cell_pos:
            tooltip.set_text("Indicates that this " + self.name + "'s saved result has changed since the status was calculated. " + \
                             "It's therefore recommended to recompute the status.")
            return True
        else:
            return False


def addRefreshTips(view, *args):
    if gtk.gtk_version >= (2, 12, 0): # Tree view tooltips don't exist prior to this version
        view.set_property("has-tooltip", True)
        refreshTips = RefreshTips(*args)
        view.connect("query-tooltip", refreshTips.getTooltip)


class GUIConfig:
    def __init__(self, dynamic, allApps, defaultColours, defaultAccelerators, includePersonal=True):
        self.apps = copy(allApps)
        self.dynamic = dynamic
        self.configDir = plugins.MultiEntryDictionary()
        self.configDocs = {}
        self.setConfigDefaults(defaultColours, defaultAccelerators)
        if includePersonal:
            self.configDir.readValues(self.getAllPersonalConfigFiles(), insert=0, errorOnUnknown=0)

        self.hiddenCategories = map(self.getConfigName, self.configDir.get("hide_test_category"))
        self.colourDict = self.makeColourDictionary()
        
    def getAllPersonalConfigFiles(self):
        allPersonalFiles = []
        # Always include app-independent version
        appIndep = os.path.join(plugins.getPersonalConfigDir(), "config")
        if os.path.isfile(appIndep):
            allPersonalFiles.append(appIndep)
        for app in self.apps:
            for fileName in app.getPersonalConfigFiles():
                if not fileName in allPersonalFiles:
                    allPersonalFiles.append(fileName)
        return allPersonalFiles
    
    def addSuites(self, suites):
        fullNames = [ app.fullName() for app in self.apps ]
        for suite in suites:
            if suite.app.fullName() not in fullNames:
                self.apps.append(suite.app)

    def makeColourDictionary(self):
        dict = {}
        for key, value in self.configDir.get("test_colours").items():
            dict[self.getConfigName(key)] = value
        return dict

    def setConfigDefaults(self, colourDict, accelerators):
        self.setConfigDefault("static_collapse_suites", 0, "Whether or not the static GUI will show everything collapsed")
        self.setConfigDefault("test_colours", colourDict, "Colours to use for each test state")
        self.setConfigDefault("file_colours", copy(colourDict), "Colours to use for each file state")
        self.setConfigDefault("auto_collapse_successful", 1, "Automatically collapse successful test suites?")
        self.setConfigDefault("window_size", self.getWindowSizeSettings(), "To set the initial size of the dynamic/static GUI.")
        self.setConfigDefault("hide_gui_element", self.getDefaultHideWidgets(), "List of widgets to hide by default")
        self.setConfigDefault("hide_test_category", [], "Categories of tests which should not appear in the dynamic GUI test view")
        self.setConfigDefault("query_kill_processes", { "default" : [], "static" : [ "Dynamic GUI" ] }, "Ask about whether to kill these processes when exiting texttest.")
        self.setConfigDefault("gui_accelerators", accelerators, "Custom action accelerators.")        
        self.setConfigDefault("gui_entry_completion_matching", 1, "Which matching type to use for entry completion. 0 means turn entry completions off, 1 means match the start of possible completions, 2 means match any part of possible completions")
        self.setConfigDefault("gui_entry_completion_inline", 0, "Automatically inline common completion prefix in entry.")
        self.setConfigDefault("gui_entry_completions", { "default" : [] }, "Add these completions to the entry completion lists initially")
        self.setConfigDefault("sort_test_suites_recursively", 1, "Sort subsuites when sorting test suites")
        
    def setConfigDefault(self, key, value, docString):
        self.configDir[key] = value
        self.configDocs[key] = docString

    def _simpleValue(self, app, entryName):
        return app.getConfigValue(entryName)

    def _compositeValue(self, app, *args, **kwargs):
        return app.getCompositeConfigValue(*args, **kwargs)

    def _getFromApps(self, method, *args, **kwargs):
        callables = [ plugins.Callable(method, app, *args) for app in self.apps ]
        aggregator = plugins.ResponseAggregator(callables)
        try:
            return aggregator(**kwargs)
        except plugins.AggregationError, e:
            app = self.apps[e.index]
            plugins.printWarning("GUI configuration '" + "::".join(args) +\
                                 "' differs between applications, ignoring that from " + repr(app) + "\n" + \
                                 "Value was " + repr(e.value2) + ", change from " + repr(e.value1), stdout=True)
            return e.value1
    
    def getModeName(self):
        if self.dynamic:
            return "dynamic"
        else:
            return "static"

    def getConfigName(self, name, modeDependent=False):
        formattedName = name.lower().replace(" ", "_").replace(":", "_")
        if modeDependent:
            if len(name) > 0:
                return self.getModeName() + "_" + formattedName
            else:
                return self.getModeName()
        else:
            return formattedName
        
    def getValue(self, entryName, modeDependent=False):
        nameToUse = self.getConfigName(entryName, modeDependent)
        guiValue = self.configDir.get(nameToUse)
        if guiValue is not None:
            return guiValue
        else:
            return self._getFromApps(self._simpleValue, nameToUse)
    def getCompositeValue(self, sectionName, entryName, modeDependent=False, defaultKey="default"):
        nameToUse = self.getConfigName(entryName, modeDependent)
        value = self.configDir.getComposite(sectionName, nameToUse, defaultKey=defaultKey)
        if value is None:
            value = self._getFromApps(self._compositeValue, sectionName, nameToUse, defaultKey=defaultKey)
        if modeDependent and value is None:
            return self.getCompositeValue(sectionName, entryName)
        else:
            return value
    def getWindowOption(self, name):
        return self.getCompositeValue("window_size", name, modeDependent=True)
    def showCategoryByDefault(self, category, parentHidden=False):
        if self.dynamic:
            if parentHidden:
                return False
            nameToUse = self.getConfigName(category)
            if nameToUse in self.hiddenCategories:
                return False
            else:
                return True
        else:
            return False    
    def getTestColour(self, category, fallback=None):
        if self.dynamic:
            nameToUse = self.getConfigName(category)
            if self.colourDict.has_key(nameToUse):
                return self.colourDict[nameToUse]
            elif fallback:
                return fallback
            else:
                return self.colourDict.get("failure")
        else:
            if category.startswith("clipboard"):
                return self.colourDict.get(category)
            else:
                return self.colourDict.get("static")

    @staticmethod
    def getWindowSizeSettings():
        dict = {}
        dict["maximize"] = 0
        dict["horizontal_separator_position"] = 0.46
        dict["vertical_separator_position"] = 0.5
        dict["height_pixels"] = "<not set>"
        dict["width_pixels"] = "<not set>"
        dict["height_screen"] = float(5.0) / 6
        dict["width_screen"] = 0.6
        return dict

    @staticmethod
    def getDefaultHideWidgets():
        dict = {}
        dict["status_bar"] = 0
        dict["toolbar"] = 0
        dict["shortcut_bar"] = 0
        return dict

    @staticmethod
    def getDefaultColours():
        dict = {}
        dict["default"] = "salmon"
        dict["success"] = "DarkSeaGreen2"
        dict["failure"] = "salmon"
        dict["running"] = "LightGoldenrod1"
        dict["initial_filter"] = "LightGoldenrod1"
        dict["final_filter"] = "LightGoldenrod1"
        dict["not_started"] = "white"
        dict["pending"] = "grey80"
        dict["static"] = "grey90"
        dict["clipboard_cut"] = "red"
        dict["clipboard_copy"] = "grey60"
        dict["marked"] = "orange"
        return dict


# base class for all "GUI" classes which manage parts of the display
class SubGUI(plugins.Observable):
    def __init__(self):
        plugins.Observable.__init__(self)
        self.widget = None
    
    def createView(self): # pragma: no cover - implemented in all subclasses
        pass

    def shouldShow(self):
        return True # should this be shown/created at all this run

    def shouldShowCurrent(self, *args):
        return True # should this be shown or hidden in the current context?

    def getTabTitle(self):
        return ""

    def forceVisible(self, *args):
        return False

    def addScrollBars(self, view, hpolicy):
        window = gtk.ScrolledWindow()
        window.set_policy(hpolicy, gtk.POLICY_AUTOMATIC)
        self.addToScrolledWindow(window, view)
        window.show()
        return window

    def addToScrolledWindow(self, window, widget):
        if isinstance(widget, gtk.VBox):
            window.add_with_viewport(widget)
        else:
            window.add(widget)

    def applicationEvent(self, name, **kw):
        try:
            from storytext import applicationEvent
            # Everything that comes from here is to do with editing files in external programs
            applicationEvent(name, "files", **kw)
        except ImportError:
            pass


# base class for managing containers
class ContainerGUI(SubGUI):
    def __init__(self, subguis):
        SubGUI.__init__(self)
        self.subguis = subguis

    def forceVisible(self, rowCount):
        return reduce(operator.or_, (subgui.forceVisible(rowCount) for subgui in self.subguis))

    def shouldShow(self):
        return reduce(operator.or_, (subgui.shouldShow() for subgui in self.subguis))

    def shouldShowCurrent(self, *args):
        return reduce(operator.and_, (subgui.shouldShowCurrent(*args) for subgui in self.subguis))

    def getTabTitle(self):
        return self.subguis[0].getTabTitle()
