
""" 
The various "holders" for displaying the "ActionGUI" abstraction: i.e. menus, toolbars and popups,
to store the simple actions and the dialogs, and a notebook to store the tabs in.
"""

import gtk, guiutils, plugins, os, sys, logging, types
from ordereddict import OrderedDict

class MenuBarGUI(guiutils.SubGUI):
    def __init__(self, dynamic, uiManager, actionGUIs, menuNames, *args):
        guiutils.SubGUI.__init__(self)
        # Create GUI manager, and a few default action groups
        self.menuNames = menuNames
        self.dynamic = dynamic
        self.allFiles = plugins.findDataPaths([ "*.xml" ], *args)
        self.uiManager = uiManager
        self.actionGUIs = actionGUIs
        self.actionGroup = self.uiManager.get_action_groups()[0]
        self.toggleActions = []
        self.loadedModules = set()
        self.diag = logging.getLogger("Menu Bar")
        self.diag.info("All description files : " + repr(self.allFiles))

    def getLoadedModules(self):
        if not self.loadedModules:
            self.loadedModules = set((module.split(".")[-1] for module in sys.modules.keys()))
        return self.loadedModules
    
    def shouldHide(self, name):
        return guiutils.guiConfig.getCompositeValue("hide_gui_element", name, modeDependent=True)

    def toggleVisibility(self, action, observer, *args):
        widget = observer.widget
        oldVisible = widget.get_property('visible')
        newVisible = action.get_active()
        if oldVisible and not newVisible:
            widget.hide()
        elif newVisible and not oldVisible:
            widget.show()

    def createToggleActions(self):
        for observer in self.observers:
            actionTitle = observer.getWidgetName()
            actionName = actionTitle.replace("_", "")
            gtkAction = gtk.ToggleAction(actionName, actionTitle, None, None)
            if observer.shouldShow():
                gtkAction.set_active(True)
            else:
                gtkAction.set_sensitive(False)
            self.actionGroup.add_action(gtkAction)
            gtkAction.connect("toggled", self.toggleVisibility, observer)
            self.toggleActions.append(gtkAction)
            
    def createView(self):
        # Initialize
        for menuName in self.menuNames:
            realMenuName = menuName
            if not menuName.isupper():
                realMenuName = menuName.capitalize()
            self.actionGroup.add_action(gtk.Action(menuName + "menu", "_" + realMenuName, None, None))
        self.createToggleActions()

        for file in self.getGUIDescriptionFileNames():
            try:
                self.diag.info("Reading UI from file " + file)
                self.uiManager.add_ui_from_file(file)
            except Exception, e:
                raise plugins.TextTestError, "Failed to parse GUI description file '" + file + "': " + str(e)
        self.uiManager.ensure_update()
        self.widget = self.uiManager.get_widget("/MainMenuBar")
        return self.widget
    
    def notifyTopWindow(self, window):
        window.add_accel_group(self.uiManager.get_accel_group())
        if self.shouldHide("menubar"):
            self.widget.hide()
        for toggleAction in self.toggleActions:
            if self.shouldHide(toggleAction.get_name()):
                toggleAction.set_active(False)

    def getGUIDescriptionFileNames(self):
        # Pick up all GUI descriptions corresponding to modules we've loaded
        loadFiles = filter(self.shouldLoad, self.allFiles)
        loadFiles.sort(self.cmpDescFiles)
        return loadFiles

    def cmpDescFiles(self, file1, file2):
        base1 = os.path.basename(file1)
        base2 = os.path.basename(file2)
        default1 = base1.startswith("default")
        default2 = base2.startswith("default")
        if default1 != default2:
            return cmp(default2, default1)
        partCount1 = base1.count("-")
        partCount2 = base2.count("-")
        if partCount1 != partCount2:
            return cmp(partCount1, partCount2) # less - implies read first (not mode-specific)
        return cmp(base2, base1) # something deterministic, just to make sure it's the same for everyone
    
    def shouldLoad(self, fileName):
        # Infer whether a file should be loaded
        # The format is
        # <module_name>-<config setting>-<config setting...>-[|dynamic|static].xml
        allParts = os.path.basename(fileName)[:-4].split("-") # drop .xml, split on "-"
        moduleName = allParts[0]
        if allParts[-1] == "dynamic":
            if self.dynamic:
                allParts = allParts[:-1]
            else:
                return False
        elif allParts[-1] == "static":
            if self.dynamic:
                return False
            else:
                allParts = allParts[:-1]

        self.diag.info("Checking if we loaded module " + moduleName)
        if moduleName not in self.getLoadedModules():
            return False

        for configSetting in allParts[1:]:
            value = guiutils.guiConfig.getValue(configSetting)
            self.diag.info("Checking if we have set " + configSetting + " = " + repr(value))
            if not self.haveSet(value):
                return False
        return True

    def haveSet(self, val):
        if type(val) == types.DictType:
            if len(val) == 1:
                if val.has_key(""):
                    return val[""]
                elif val.has_key("default"):
                    return val["default"]
            else:
                return True
        else:
            return bool(value)

        
    

class ToolBarGUI(guiutils.ContainerGUI):
    def __init__(self, uiManager, subgui):
        guiutils.ContainerGUI.__init__(self, [ subgui ])
        self.uiManager = uiManager
    def getWidgetName(self):
        return "_Toolbar"
    def ensureVisible(self, toolbar):
        for item in toolbar.get_children():
            item.set_is_important(True) # Or newly added children without stock ids won't be visible in gtk.TOOLBAR_BOTH_HORIZ style
    def shouldShow(self):
        return True # don't care about whether we have a progress bar or not
    def createView(self):
        self.uiManager.ensure_update()
        toolbar = self.uiManager.get_widget("/MainToolBar")
        self.ensureVisible(toolbar)

        self.widget = gtk.HandleBox()
        self.widget.add(toolbar)
        toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        progressBarGUI = self.subguis[0]
        if progressBarGUI.shouldShow():
            progressBar = progressBarGUI.createView()
            width = 7 # Looks good, same as gtk.Paned border width
            alignment = gtk.Alignment()
            alignment.set(1.0, 1.0, 1.0, 1.0)
            alignment.set_padding(width, width, 1, width)
            alignment.add(progressBar)
            toolItem = gtk.ToolItem()
            toolItem.add(alignment)
            toolItem.set_expand(True)
            toolbar.insert(toolItem, -1)

        self.widget.show_all()
        return self.widget

def createPopupGUIs(uiManager):
    return PopupMenuGUI("TestPopupMenu", uiManager), PopupMenuGUI("TestFilePopupMenu", uiManager)

class PopupMenuGUI(guiutils.SubGUI):
    def __init__(self, name, uiManager):
        guiutils.SubGUI.__init__(self)
        self.name = name
        self.uiManager = uiManager
    def createView(self):
        self.uiManager.ensure_update()
        self.widget = self.uiManager.get_widget("/" + self.name)
        self.widget.show_all()
        return self.widget
    def showMenu(self, treeview, event):
        if event.button == 3 and len(self.widget.get_children()) > 0:
            time = event.time
            pathInfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            selection = treeview.get_selection()
            selectedRows = selection.get_selected_rows()
            # If they didnt right click on a currently selected
            # row, change the selection
            if pathInfo is not None:
                if pathInfo[0] not in selectedRows[1]:
                    selection.unselect_all()
                    selection.select_path(pathInfo[0])
                treeview.grab_focus()
                self.widget.popup(None, None, None, event.button, time)
                treeview.emit_stop_by_name("button-press-event")
                

class NotebookGUI(guiutils.SubGUI):
    def __init__(self, tabInfo):
        guiutils.SubGUI.__init__(self)
        self.diag = logging.getLogger("GUI notebook")
        self.tabInfo = filter(lambda tabGUI: tabGUI.shouldShow(), tabInfo)
        self.notebook = None
        self.currentTabGUI = self.findInitialCurrentTab()
        self.diag.info("Current page set to '" + self.currentTabGUI.getTabTitle() + "'")

    def createView(self):
        self.notebook = gtk.Notebook()
        self.notebook.set_name("main right-hand notebook")
        for tabGUI in self.tabInfo:
            tabName = tabGUI.getTabTitle()
            label = gtk.Label(tabName)
            page = self.createPage(tabGUI, tabName)
            self.notebook.append_page(page, label)

        self.notebook.set_scrollable(True)
        self.notebook.show()
        self.notebook.connect("switch-page", self.pageSwitched)
        return self.notebook

    def createPage(self, tabGUI, tabName):
        self.diag.info("Adding page " + tabName)
        page = tabGUI.createView()
        if not tabGUI.shouldShowCurrent():
            self.diag.info("Hiding page " + tabName)
            page.hide()
        return page

    def findInitialCurrentTab(self):
        for tabGUI in self.tabInfo:
            if tabGUI.shouldShowCurrent():
                return tabGUI

    def findFirstRemaining(self, pagesRemoved):
        for page in self.notebook.get_children():
            if page.get_property("visible"):
                pageNum = self.notebook.page_num(page)
                if not pagesRemoved.has_key(pageNum):
                    return pageNum

    def showNewPages(self, *args):
        changed = False
        for pageNum, tabGUI in enumerate(self.tabInfo):
            page = self.notebook.get_nth_page(pageNum)
            name = tabGUI.getTabTitle()
            if tabGUI.shouldShowCurrent(*args):
                if not page.get_property("visible"):
                    self.diag.info("Showing page " + name)
                    page.show()
                    changed = True
            else:
                self.diag.info("Remaining hidden " + name)
        return changed
    
    def pageSwitched(self, dummy, dummy2, newNum, *args):
        newTabGUI = self.tabInfo[newNum]
        self.diag.info("Resetting current page to page " + repr(newNum) + " = " + repr(newTabGUI.getTabTitle()))
        # Must do this afterwards, otherwise the above change doesn't propagate
        self.currentTabGUI = newTabGUI
        self.diag.info("Resetting done.")

    def findPagesToHide(self, *args):
        pages = OrderedDict()
        for pageNum, tabGUI in enumerate(self.tabInfo):
            page = self.notebook.get_nth_page(pageNum)
            if not tabGUI.shouldShowCurrent(*args) and page.get_property("visible"):
                pages[pageNum] = page
        return pages

    def hideOldPages(self, *args):
        # Must reset the current page before removing it if we're viewing a removed page
        # otherwise we can output lots of pages we don't really look at
        pagesToHide = self.findPagesToHide(*args)
        if len(pagesToHide) == 0:
            return False

        if pagesToHide.has_key(self.notebook.get_current_page()):
            newCurrentPageNum = self.findFirstRemaining(pagesToHide)
            if newCurrentPageNum is not None:
                self.notebook.set_current_page(newCurrentPageNum)

        # remove from the back, so we don't momentarily view them all if removing everything
        for page in reversed(pagesToHide.values()):
            self.diag.info("Hiding page " + self.notebook.get_tab_label_text(page))
            page.hide()
        return True

    def updateCurrentPage(self, rowCount):
        for pageNum, tabGUI in enumerate(self.tabInfo):
            if tabGUI.shouldShowCurrent() and tabGUI.forceVisible(rowCount):
                return self.notebook.set_current_page(pageNum)

    def notifyNewTestSelection(self, tests, dummyApps, rowCount, direct):
        # This is mostly an attempt to work around the tree search problems.
        # Don't hide the tab for user-deselections of all tests because it trashes the search.
        if len(tests) > 0 or not direct:
            self.diag.info("New selection with " + repr(tests) + ", adjusting notebook")
            # only change pages around if a test is directly selected and we haven't already selected another important tab
            changeCurrentPage = direct and not self.currentTabGUI.forceVisible(rowCount)
            self.diag.info("Current tab gui " + repr(self.currentTabGUI.__class__) + " will change = " + repr(changeCurrentPage))
            self.updatePages(rowCount=rowCount, changeCurrentPage=changeCurrentPage)

    def updatePages(self, test=None, state=None, rowCount=0, changeCurrentPage=False):
        if not self.notebook:
            return
        self.showNewPages(test, state)
        self.hideOldPages(test, state)
        if changeCurrentPage:
            self.updateCurrentPage(rowCount)

    def notifyLifecycleChange(self, test, state, *args):
        self.updatePages(test, state)

    def addSuites(self, *args):
        self.updatePages()
