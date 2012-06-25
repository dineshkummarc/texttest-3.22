
"""
Code associated with the left-hand tree view for tests 
"""

import gtk, gobject, pango, guiutils, plugins, logging
from ordereddict import OrderedDict

class TestColumnGUI(guiutils.SubGUI):
    def __init__(self, dynamic, testCount):
        guiutils.SubGUI.__init__(self)
        self.addedCount = 0
        self.totalNofTests = testCount
        self.totalNofDistinctTests = testCount
        self.nofSelectedTests = 0
        self.nofDistinctSelectedTests = 0
        self.totalNofTestsShown = 0
        self.versionString = ""
        self.column = None
        self.dynamic = dynamic
        self.testSuiteSelection = False
        self.diag = logging.getLogger("Test Column GUI")
        self.allSuites = []

    def addSuites(self, suites):
        self.allSuites = suites

    def createView(self):
        testRenderer = gtk.CellRendererText()
        self.column = gtk.TreeViewColumn(self.getTitle(), testRenderer, text=0, background=1, foreground=7)
        self.column.set_data("name", "Test Name") # Not a widget, so we can't set a name, do this instead
        self.column.set_resizable(True)
        self.column.set_cell_data_func(testRenderer, self.renderSuitesBold)
        if not self.dynamic:
            self.column.set_clickable(True)
            self.column.connect("clicked", self.columnClicked)
        if guiutils.guiConfig.getValue("auto_sort_test_suites") == 1:
            self.column.set_sort_indicator(True)
            self.column.set_sort_order(gtk.SORT_ASCENDING)
        elif guiutils.guiConfig.getValue("auto_sort_test_suites") == -1:
            self.column.set_sort_indicator(True)
            self.column.set_sort_order(gtk.SORT_DESCENDING)
        return self.column
    
    def renderSuitesBold(self, dummy, cell, model, iter):
        if model.get_value(iter, 2)[0].classId() == "test-case":
            cell.set_property('font', "")
        else:
            cell.set_property('font', "bold")

    def columnClicked(self, *args):
        if not self.column.get_sort_indicator():
            self.column.set_sort_indicator(True)
            self.column.set_sort_order(gtk.SORT_ASCENDING)
            order = 1
        else:
            order = self.column.get_sort_order()
            if order == gtk.SORT_ASCENDING:
                self.column.set_sort_order(gtk.SORT_DESCENDING)
                order = -1
            else:
                self.column.set_sort_indicator(False)
                order = 0

        self.notify("ActionStart")
        self.setSortingOrder(order)
        if order == 1:
            self.notify("Status", "Tests sorted in alphabetical order.")
        elif order == -1:
            self.notify("Status", "Tests sorted in descending alphabetical order.")
        else:
            self.notify("Status", "Tests sorted according to testsuite file.")
        self.notify("RefreshTestSelection")
        self.notify("ActionStop")
        
    def setSortingOrder(self, order, suite = None):
        if not suite:
            for suite in self.allSuites:
                self.setSortingOrder(order, suite)
        else:
            self.notify("Status", "Sorting suite " + suite.name + " ...")
            self.notify("ActionProgress")
            suite.autoSortOrder = order
            suite.updateOrder()
            for test in suite.testcases:
                if test.classId() == "test-suite":
                    self.setSortingOrder(order, test)

    def getTitle(self):
        title = "Tests: "
        if self.versionString and len(self.versionString) > 40:
            reducedVersionString = self.versionString[:40] + "..."
        else:
            reducedVersionString = self.versionString  

        if self.testSuiteSelection:              
            # We don't care about totals with test suites
            title += plugins.pluralise(self.nofSelectedTests, "suite") + " selected"
            if self.versionString:
                title += ", " + reducedVersionString
            elif self.nofDistinctSelectedTests != self.nofSelectedTests:
                title += ", " + str(self.nofDistinctSelectedTests) + " distinct"
            return title
        
        if self.nofSelectedTests == self.totalNofTests:
            title += "All " + str(self.totalNofTests) + " selected"
        else:
            title += str(self.nofSelectedTests) + "/" + str(self.totalNofTests) + " selected"

        if not self.dynamic:
            if self.versionString:
                title += ", " + reducedVersionString
            elif self.totalNofDistinctTests != self.totalNofTests:
                if self.nofDistinctSelectedTests == self.totalNofDistinctTests:
                    title += ", all " + str(self.totalNofDistinctTests) + " distinct"
                else:
                    title += ", " + str(self.nofDistinctSelectedTests) + "/" + str(self.totalNofDistinctTests) + " distinct"

        if self.totalNofTestsShown == self.totalNofTests:
            if self.dynamic and self.totalNofTests > 0:
                title += ", none hidden"
        elif self.totalNofTestsShown == 0:
            title += ", all hidden"
        else:
            title += ", " + str(self.totalNofTests - self.totalNofTestsShown) + " hidden"

        return title

    def updateTitle(self, initial=False):
        if self.column:
            self.column.set_title(self.getTitle())

    def notifyTestTreeCounters(self, totalDelta, totalShownDelta, totalRowsDelta, initial=False):
        self.addedCount += totalDelta
        if not initial or self.totalNofTests < self.addedCount:
            self.totalNofTests += totalDelta
            self.totalNofDistinctTests += totalRowsDelta
        self.totalNofTestsShown += totalShownDelta
        self.updateTitle(initial)

    def notifyAllRead(self):
        if self.addedCount != self.totalNofTests:
            self.totalNofTests = self.addedCount
            self.updateTitle()

    def countTests(self, tests):
        if self.dynamic:
            return len(tests), False
        
        testCount, suiteCount = 0, 0
        for test in tests:
            if test.classId() == "test-case":
                testCount += 1
            else:
                suiteCount += 1
        if suiteCount and not testCount:
            return suiteCount, True
        else:
            return testCount, False

    def getVersionString(self, tests, distinctTestCount):
        if not self.dynamic and distinctTestCount == 1 and self.totalNofTests != self.totalNofDistinctTests:
            versions = [ test.app.getFullVersion().replace("_", "__") or "<default>" for test in tests ]
            return "version" + ("s" if len(versions) > 1 else "") + " " + ",".join(versions)
        else:
            return ""
                            
    def notifyNewTestSelection(self, tests, dummyApps, distinctTestCount, *args, **kw):
        newCount, suitesOnly = self.countTests(tests)
        if distinctTestCount > newCount:
            distinctTestCount = newCount
        newVersionStr = self.getVersionString(tests, distinctTestCount)
        if self.nofSelectedTests != newCount or newVersionStr != self.versionString or \
               self.nofDistinctSelectedTests != distinctTestCount or suitesOnly != self.testSuiteSelection:
            self.diag.info("New selection " + repr(tests) + " distinct " + str(distinctTestCount))
            self.nofSelectedTests = newCount
            self.nofDistinctSelectedTests = distinctTestCount
            self.testSuiteSelection = suitesOnly
            self.versionString = newVersionStr
            self.updateTitle()
            
    def notifyVisibility(self, tests, newValue):
        testCount = sum((int(test.classId() == "test-case") for test in tests))
        if newValue:
            self.totalNofTestsShown += testCount
        else:
            self.totalNofTestsShown -= testCount
        self.updateTitle()


class TestIteratorMap:
    def __init__(self, dynamic, allApps):
        self.dict = OrderedDict()
        self.dynamic = dynamic
        self.parentApps = {}
        for app in allApps:
            for extra in [ app ] + app.extras:
                self.parentApps[extra] = app
    def getKey(self, test):
        if self.dynamic:
            return test
        elif test is not None:
            return self.parentApps.get(test.app, test.app), test.getRelPath()
    def store(self, test, iter):
        self.dict[self.getKey(test)] = iter
    def updateIterator(self, test, oldRelPath):
        # relative path of test has changed
        key = self.parentApps.get(test.app, test.app), oldRelPath
        iter = self.dict.get(key)
        if iter is not None:
            self.store(test, iter)
            del self.dict[key]
            return iter
        else:
            return self.getIterator(test)

    def getIterator(self, test):
        return self.dict.get(self.getKey(test))

    def remove(self, test):
        key = self.getKey(test)
        if self.dict.has_key(key):
            del self.dict[key]


class TestTreeGUI(guiutils.ContainerGUI):
    def __init__(self, dynamic, allApps, popupGUI, subGUI):
        guiutils.ContainerGUI.__init__(self, [ subGUI ])
        self.model = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_PYOBJECT,\
                                   gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, \
                                   gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.popupGUI = popupGUI
        self.itermap = TestIteratorMap(dynamic, allApps)
        self.selection = None
        self.selecting = False
        self.selectedTests = []
        self.clipboardTests = set()
        self.dynamic = dynamic
        self.collapseStatic = self.getCollapseStatic()
        self.successPerSuite = {} # map from suite to tests succeeded
        self.collapsedRows = {}
        self.filteredModel = None
        self.treeView = None
        self.newTestsVisible = guiutils.guiConfig.showCategoryByDefault("not_started")
        self.diag = logging.getLogger("Test Tree")

    def notifyDefaultVisibility(self, newValue):
        self.newTestsVisible = newValue

    def isExpanded(self, iter):
        parentIter = self.filteredModel.iter_parent(iter)
        return not parentIter or self.treeView.row_expanded(self.filteredModel.get_path(parentIter))

    def getCollapseStatic(self):
        if self.dynamic:
            return False
        else:
            return guiutils.guiConfig.getValue("static_collapse_suites")

    def notifyAllRead(self, *args):
        if self.dynamic:
            self.filteredModel.connect('row-inserted', self.rowInserted)
        else:
            self.newTestsVisible = True
            self.model.foreach(self.makeRowVisible)
            if self.collapseStatic:
                self.expandLevel(self.treeView, self.filteredModel.get_iter_root())
            else:
                self.treeView.expand_all()
        self.notify("AllRead")
        
    def makeRowVisible(self, model, dummyPath, iter):
        model.set_value(iter, 5, True)

    def getNodeName(self, suite, parent):
        nodeName = suite.name
        if parent == None:
            appName = suite.app.name + suite.app.versionSuffix()
            if appName != nodeName:
                nodeName += " (" + appName + ")"
        return nodeName

    def addSuiteWithParent(self, suite, parent, follower=None):
        nodeName = self.getNodeName(suite, parent)
        self.diag.info("Adding node with name " + nodeName)
        colour = guiutils.guiConfig.getTestColour("not_started")
        row = [ nodeName, colour, [ suite ], "", colour, self.newTestsVisible, "", "black" ]
        iter = self.model.insert_before(parent, follower, row)
        storeIter = iter.copy()
        self.itermap.store(suite, storeIter)
        path = self.model.get_path(iter)
        if self.newTestsVisible and parent is not None:
            filterPath = self.filteredModel.convert_child_path_to_path(path)
            self.treeView.expand_to_path(filterPath)
        return iter
    
    def createView(self):
        self.filteredModel = self.model.filter_new()
        self.filteredModel.set_visible_column(5)
        self.treeView = gtk.TreeView(self.filteredModel)
        self.treeView.set_search_column(0)
        self.treeView.set_name("Test Tree")
        self.treeView.expand_all()

        self.selection = self.treeView.get_selection()
        self.selection.set_mode(gtk.SELECTION_MULTIPLE)
        if self.dynamic:
            self.selection.set_select_function(self.canSelect)

        testsColumn = self.subguis[0].createView()
        self.treeView.append_column(testsColumn)
        if self.dynamic:
            detailsRenderer = gtk.CellRendererText()
            detailsRenderer.set_property('wrap-width', 350)
            detailsRenderer.set_property('wrap-mode', pango.WRAP_WORD_CHAR)
            recalcRenderer = gtk.CellRendererPixbuf()
            detailsColumn = gtk.TreeViewColumn("Details")
            detailsColumn.pack_start(detailsRenderer, expand=True)
            detailsColumn.pack_start(recalcRenderer, expand=False)
            detailsColumn.add_attribute(detailsRenderer, 'text', 3)
            detailsColumn.add_attribute(detailsRenderer, 'background', 4)
            detailsColumn.add_attribute(recalcRenderer, 'stock_id', 6)
            detailsColumn.set_resizable(True)
            guiutils.addRefreshTips(self.treeView, "test", recalcRenderer, detailsColumn, 6)
            self.treeView.append_column(detailsColumn)

        self.treeView.connect('row-expanded', self.rowExpanded)
        self.expandLevel(self.treeView, self.filteredModel.get_iter_root())
        self.treeView.connect("button_press_event", self.popupGUI.showMenu)
        self.selection.connect("changed", self.userChangedSelection)

        self.treeView.show()

        self.popupGUI.createView()
        return self.addScrollBars(self.treeView, hpolicy=gtk.POLICY_NEVER)
    
    def notifyTopWindow(self, *args):
        # avoid the quit button getting initial focus, give it to the tree view (why not?)
        self.treeView.grab_focus()

    def canSelect(self, path):
        pathIter = self.filteredModel.get_iter(path)
        test = self.filteredModel.get_value(pathIter, 2)[0]
        return test.classId() == "test-case"

    def rowExpanded(self, treeview, iter, path):
        if self.dynamic:
            realPath = self.filteredModel.convert_path_to_child_path(path)
            if self.collapsedRows.has_key(realPath):
                del self.collapsedRows[realPath]
        self.expandLevel(treeview, self.filteredModel.iter_children(iter), not self.collapseStatic)

    def rowInserted(self, model, dummy, iter):
        self.expandRow(model.iter_parent(iter), False)

    def expandRow(self, iter, recurse):
        if iter == None:
            return
        path = self.filteredModel.get_path(iter)
        realPath = self.filteredModel.convert_path_to_child_path(path)

        # Iterate over children, call self if they have children
        if not self.collapsedRows.has_key(realPath):
            self.diag.info("Expanding path at " + repr(realPath))
            self.treeView.expand_row(path, open_all=False)
        if recurse:
            childIter = self.filteredModel.iter_children(iter)
            while (childIter != None):
                if self.filteredModel.iter_has_child(childIter):
                    self.expandRow(childIter, True)
                childIter = self.filteredModel.iter_next(childIter)

    def collapseRow(self, iter):
        # To make sure that the path is marked as 'collapsed' even if the row cannot be collapsed
        # (if the suite is empty, or not shown at all), we set self.collapsedRow manually, instead of
        # waiting for rowCollapsed() to do it at the 'row-collapsed' signal (which will not be emitted
        # in the above cases)
        path = self.model.get_path(iter)
        self.diag.info("Collapsed path " + repr(path))
        self.collapsedRows[path] = 1
        # Collapsing rows can cause indirect changes of selection, make sure we indicate this.
        self.selecting = True
        filterPath = self.filteredModel.convert_child_path_to_path(path)
        if filterPath is not None: # don't collapse if it's already hidden
            self.selection.get_tree_view().collapse_row(filterPath)
        self.selecting = False
        self.selectionChanged(direct=False)

    def userChangedSelection(self, *args):
        if not self.selecting and not hasattr(self.selection, "unseen_changes"):
            self.selectionChanged(direct=True)
            
    def selectionChanged(self, direct):
        newSelection = self.getSelected()
        if newSelection != self.selectedTests:
            self.sendSelectionNotification(newSelection, direct)
            if self.dynamic and direct:
                self.selection.selected_foreach(self.updateRecalculationMarker)

    def notifyRefreshTestSelection(self):
        # The selection hasn't changed, but we want to e.g.
        # recalculate the action sensitiveness and make sure we can still see the selected tests.
        self.sendSelectionNotification(self.selectedTests)
        self.scrollToFirstTest()
        
    def notifyRecomputed(self, test):
        iter = self.itermap.getIterator(test)
        # If we've recomputed, clear the recalculation icons
        self.setNewRecalculationStatus(iter, test, [])
        if test.stateInGui.hasFailed():
            self.removeFromSuiteSuccess(test)            

    def getSortedSelectedTests(self, suite):
        appTests = filter(lambda test: test.app is suite.app, self.selectedTests)
        allTests = suite.allTestsAndSuites()
        appTests.sort(key=allTests.index)
        return appTests

    def notifyWriteTestsIfSelected(self, suite, file):
        for test in self.getSortedSelectedTests(suite):
            self.writeSelectedTest(test, file)

    def shouldListSubTests(self, test):
        if test.parent is None or not all((self.isVisible(test) for test in test.testCaseList())):
            return True

        filters = test.app.getFilterList([test])
        return len(filters) > 0

    def writeSelectedTest(self, test, file):
        if test.classId() == "test-suite":
            if self.shouldListSubTests(test):
                for subTest in test.testcases:
                    if self.isVisible(subTest):
                        self.writeSelectedTest(subTest, file)
                return    
        file.write(test.getRelPath() + "\n")        
        
    def updateRecalculationMarker(self, model, dummy, iter):
        tests = model.get_value(iter, 2)
        if not tests[0].stateInGui.isComplete():
            return

        recalcComparisons = tests[0].stateInGui.getComparisonsForRecalculation()
        childIter = self.filteredModel.convert_iter_to_child_iter(iter)
        self.setNewRecalculationStatus(childIter, tests[0], recalcComparisons)

    def setNewRecalculationStatus(self, iter, test, recalcComparisons):
        oldVal = self.model.get_value(iter, 6)
        newVal = self.getRecalculationIcon(recalcComparisons)
        if newVal != oldVal:
            self.model.set_value(iter, 6, newVal)
        self.notify("Recalculation", test, recalcComparisons, newVal)

    def getRecalculationIcon(self, recalc):
        if recalc:
            return "gtk-refresh"
        else:
            return ""

    def checkRelatedForRecalculation(self, test):
        self.filteredModel.foreach(self.checkRecalculationIfMatches, test)

    def checkRecalculationIfMatches(self, model, path, iter, test):
        tests = model.get_value(iter, 2)
        if tests[0] is not test and tests[0].getRelPath() == test.getRelPath():
            self.updateRecalculationMarker(model, path, iter)

    def getSelectedApps(self, tests):
        apps = []
        for test in tests:
            if test.app not in apps:
                apps.append(test.app)
        return apps

    def sendSelectionNotification(self, tests, direct=True):
        self.diag.info("Selection now changed to " + repr(tests))
        apps = self.getSelectedApps(tests)
        self.selectedTests = tests
        self.notify("NewTestSelection", tests, apps, self.selection.count_selected_rows(), direct)

    def getSelected(self):
        allSelected = []
        prevSelected = set(self.selectedTests)
        def addSelTest(model, dummy, iter, selected):
            selected += self.getNewSelected(model.get_value(iter, 2), prevSelected)

        self.selection.selected_foreach(addSelTest, allSelected)
        self.diag.info("Selected tests are " + repr(allSelected))
        return allSelected

    def getNewSelected(self, tests, prevSelected):
        intersection = prevSelected.intersection(set(tests))
        if len(intersection) == 0 or len(intersection) == len(tests) or len(intersection) == len(prevSelected):
            return tests
        else:
            return list(intersection)
        
    def findIter(self, test):
        try:
            childIter = self.itermap.getIterator(test)
            if childIter:
                return self.filteredModel.convert_child_iter_to_iter(childIter)
        except RuntimeError:
            pass # convert_child_iter_to_iter throws RunTimeError if the row is hidden in the TreeModelFilter

    def notifySetTestSelection(self, selTests, criteria="", selectCollapsed=True):
        actualSelection = self.selectTestRows(selTests, selectCollapsed)
        # Here it's been set via some indirect mechanism, might want to behave differently
        self.sendSelectionNotification(actualSelection, direct=False)

    def selectTestRows(self, selTests, selectCollapsed=True):
        self.selecting = True # don't respond to each individual programmatic change here
        self.selection.unselect_all()
        treeView = self.selection.get_tree_view()
        firstPath = None
        actuallySelected = []
        for test in selTests:
            iter = self.findIter(test)
            if not iter or (not selectCollapsed and not self.isExpanded(iter)):
                continue

            actuallySelected.append(test)
            path = self.filteredModel.get_path(iter)
            if not firstPath:
                firstPath = path
            if selectCollapsed:
                treeView.expand_to_path(path)
            self.selection.select_iter(iter)
        treeView.grab_focus()
        if firstPath is not None and treeView.get_property("visible"):
            self.scrollToPath(firstPath)
        self.selecting = False
        return actuallySelected

    def scrollToFirstTest(self):
        if len(self.selectedTests) > 0:
            test = self.selectedTests[0]
            iter = self.findIter(test)
            path = self.filteredModel.get_path(iter)
            self.scrollToPath(path)
        
    def scrollToPath(self, path):
        treeView = self.selection.get_tree_view()
        cellArea = treeView.get_cell_area(path, treeView.get_columns()[0])
        visibleArea = treeView.get_visible_rect()
        if cellArea.y < 0 or cellArea.y > visibleArea.height:
            treeView.scroll_to_cell(path, use_align=True, row_align=0.1)

    def expandLevel(self, view, iter, recursive=True):
        # Make sure expanding expands everything, better than just one level as default...
        # Avoid using view.expand_row(path, open_all=True), as the open_all flag
        # doesn't seem to send the correct 'row-expanded' signal for all rows ...
        # This way, the signals are generated one at a time and we call back into here.
        model = view.get_model()
        while (iter != None):
            if recursive:
                view.expand_row(model.get_path(iter), open_all=False)

            iter = view.get_model().iter_next(iter)

    def notifyTestAppearance(self, test, detailText, colour1, colour2, updateSuccess, saved):
        iter = self.itermap.getIterator(test)
        self.model.set_value(iter, 1, colour1)
        self.model.set_value(iter, 3, detailText)
        self.model.set_value(iter, 4, colour2)
        if updateSuccess:
            self.updateSuiteSuccess(test, colour1)
        if saved:
            self.checkRelatedForRecalculation(test)

    def notifyLifecycleChange(self, test, *args):
        if test in self.selectedTests:
            self.notify("LifecycleChange", test, *args)
            
    def notifyFileChange(self, test, *args):
        if test in self.selectedTests:
            self.notify("FileChange", test, *args)

    def notifyDescriptionChange(self, test, *args):
        if test in self.selectedTests:
            self.notify("DescriptionChange", test, *args)

    def notifyRefreshFilePreviews(self, test, *args):
        if test in self.selectedTests:
            self.notify("RefreshFilePreviews", test, *args)

    def updateSuiteSuccess(self, test, colour):
        suite = test.parent
        if not suite:
            return

        self.successPerSuite.setdefault(suite, set()).add(test)
        successCount = len(self.successPerSuite.get(suite))
        suiteSize = len(filter(lambda subtest: not subtest.isEmpty(), suite.testcases))
        if successCount == suiteSize:
            self.setAllSucceeded(suite, colour)
            self.updateSuiteSuccess(suite, colour)

    def removeFromSuiteSuccess(self, test):
        suite = test.parent
        if suite and suite in self.successPerSuite and test in self.successPerSuite[suite]:
            self.successPerSuite[suite].remove(test)
            self.clearAllSucceeded(suite)
            self.removeFromSuiteSuccess(suite)

    def setAllSucceeded(self, suite, colour):
        # Print how many tests succeeded, color details column in success color,
        # collapse row, and try to collapse parent suite.
        detailText = "All " + str(suite.size()) + " tests successful"
        iter = self.itermap.getIterator(suite)
        self.model.set_value(iter, 3, detailText)
        self.model.set_value(iter, 4, colour)

        if guiutils.guiConfig.getValue("auto_collapse_successful") == 1:
            self.collapseRow(iter)

    def clearAllSucceeded(self, suite):
        iter = self.itermap.getIterator(suite)
        self.model.set_value(iter, 3, "")
        self.model.set_value(iter, 4, "white")

        if guiutils.guiConfig.getValue("auto_collapse_successful") == 1:
            path = self.model.get_path(iter)
            if self.collapsedRows.has_key(path):
                del self.collapsedRows[path]
            filteredPath = self.filteredModel.convert_child_path_to_path(path)
            self.treeView.expand_row(filteredPath, open_all=False)

    def isVisible(self, test):
        filteredIter = self.findIter(test)
        if filteredIter:
            filteredPath = self.filteredModel.get_path(self.filteredModel.iter_parent(filteredIter))
            path = self.filteredModel.convert_path_to_child_path(filteredPath)
            return not self.collapsedRows.has_key(path)
        else:
            self.diag.info("No iterator found for " + repr(test))
            return False
        
    def findAllTests(self):
        tests = []
        self.model.foreach(self.appendTest, tests)
        return tests
    
    def appendTest(self, model, dummy, iter, tests):
        for test in model.get_value(iter, 2):
            if test.classId() == "test-case":
                tests.append(test)
                
    def getTestForAutoSelect(self):
        allTests = self.findAllTests()
        if len(allTests) == 1:
            test = allTests[0]
            if self.isVisible(test):
                return test

    def notifyAllComplete(self):
        # Window may already have been closed...
        if self.selection.get_tree_view():
            test = self.getTestForAutoSelect()
            if test:
                actualSelection = self.selectTestRows([ test ])
                self.sendSelectionNotification(actualSelection)

    def notifyAdd(self, test, initial):
        if test.classId() == "test-case":
            self.notify("TestTreeCounters", initial=initial, totalDelta=1,
                        totalShownDelta=self.getTotalShownDelta(), totalRowsDelta=self.getTotalRowsDelta(test))
        elif self.dynamic and test.isEmpty():
            return # don't show empty suites in the dynamic GUI

        self.diag.info("Adding test " + repr(test))
        self.tryAddTest(test, initial)

    def notifyClipboard(self, tests, cut=False):        
        if cut:
            colourKey = "clipboard_cut"
        else:
            colourKey = "clipboard_copy"
        colour = guiutils.guiConfig.getTestColour(colourKey)
        toRemove = self.clipboardTests.difference(set(tests))
        self.clipboardTests = set(tests)
        for test in tests:
            iter = self.itermap.getIterator(test)
            self.model.set_value(iter, 7, colour)
        for test in toRemove:
            iter = self.itermap.getIterator(test)
            if iter:
                self.model.set_value(iter, 7, "black")

    def getTotalRowsDelta(self, test):
        if self.itermap.getIterator(test):
            return 0
        else:
            return 1

    def getTotalShownDelta(self):
        if self.dynamic:
            return int(self.newTestsVisible)
        else:
            return 1 # we hide them temporarily for performance reasons, so can't do as above

    def tryAddTest(self, test, initial=False):
        iter = self.itermap.getIterator(test)
        if iter:
            self.addAdditional(iter, test)
            return iter
        suite = test.parent
        suiteIter = None
        if suite:
            suiteIter = self.tryAddTest(suite, initial)
        followIter = self.findFollowIter(suite, test, initial)
        return self.addSuiteWithParent(test, suiteIter, followIter)
    
    def findFollowIter(self, suite, test, initial):
        if not initial and suite:
            follower = suite.getFollower(test)
            if follower:
                return self.itermap.getIterator(follower)

    def addAdditional(self, iter, test):
        currTests = self.model.get_value(iter, 2)
        if not test in currTests:
            self.diag.info("Adding additional test to node " + self.model.get_value(iter, 0))
            currTests.append(test)

    def notifyRemove(self, test):
        delta = -test.size()
        iter = self.itermap.getIterator(test)
        allTests = self.model.get_value(iter, 2)
        if len(allTests) == 1:
            self.notify("TestTreeCounters", totalDelta=delta, totalShownDelta=delta, totalRowsDelta=delta)
            self.removeTest(test, iter)
        else:
            self.notify("TestTreeCounters", totalDelta=delta, totalShownDelta=delta, totalRowsDelta=0)
            allTests.remove(test)

    def removeTest(self, test, iter):
        filteredIter = self.findIter(test)
        self.selecting = True
        if self.selection.iter_is_selected(filteredIter):
            self.selection.unselect_iter(filteredIter)
        self.selecting = False
        self.selectionChanged(direct=False)
        self.model.remove(iter)
        self.itermap.remove(test)

    def notifyNameChange(self, test, origRelPath):
        iter = self.itermap.updateIterator(test, origRelPath)
        oldName = self.model.get_value(iter, 0)
        if test.name != oldName:
            self.model.set_value(iter, 0, test.name)

        filteredIter = self.filteredModel.convert_child_iter_to_iter(iter)
        if self.selection.iter_is_selected(filteredIter):
            self.notify("NameChange", test, origRelPath)

    def notifyContentChange(self, suite):
        suiteIter = self.itermap.getIterator(suite)
        newOrder = self.findNewOrder(suiteIter)
        self.model.reorder(suiteIter, newOrder)

    def findNewOrder(self, suiteIter):
        child = self.model.iter_children(suiteIter)
        index = 0
        posMap = {}
        while (child != None):
            subTestName = self.model.get_value(child, 0)
            posMap[subTestName] = index
            child = self.model.iter_next(child)
            index += 1
        newOrder = []
        for currSuite in self.model.get_value(suiteIter, 2):
            for subTest in currSuite.testcases:
                oldIndex = posMap.get(subTest.name)
                if oldIndex not in newOrder:
                    newOrder.append(oldIndex)
        return newOrder

    def notifyVisibility(self, tests, newValue):
        self.diag.info("Visibility change for " + repr(tests) + " to " + repr(newValue))
        if not newValue:
            self.selecting = True
        changedTests = []
        for test in tests:
            if self.updateVisibilityWithParents(test, newValue):
                changedTests.append(test)

        self.selecting = False
        if len(changedTests) > 0:
            self.diag.info("Actually changed tests " + repr(changedTests))
            self.notify("Visibility", changedTests, newValue)
            if self.treeView:
                self.updateVisibilityInViews(newValue)
                
    def updateVisibilityInViews(self, newValue):
        if newValue: # if things have become visible, expand everything
            rootIter = self.filteredModel.get_iter_root()
            while rootIter != None:
                self.expandRow(rootIter, True)
                rootIter = self.filteredModel.iter_next(rootIter)
            gobject.idle_add(self.scrollToFirstTest)
        else:
            self.selectionChanged(direct=False)

    def updateVisibilityWithParents(self, test, newValue):
        changed = False
        if test.parent and newValue:
            changed |= self.updateVisibilityWithParents(test.parent, newValue)

        changed |= self.updateVisibilityInModel(test, newValue)
        if test.parent and not newValue and not self.hasVisibleChildren(test.parent):
            self.diag.info("No visible children : hiding parent " + repr(test.parent))
            changed |= self.updateVisibilityWithParents(test.parent, newValue)
        return changed

    def isMarkedVisible(self, test):
        testIter = self.itermap.getIterator(test)
        # Can get None here when using queue systems, so that some tests in a suite
        # start processing when others have not yet notified the GUI that they have been read.
        return testIter is not None and self.model.get_value(testIter, 5) and test in self.model.get_value(testIter, 2)

    def updateVisibilityInModel(self, test, newValue):
        testIter = self.itermap.getIterator(test)
        if testIter is None:
            # Tests are not necessarily loaded yet in the GUI (for example if we do show only selected), don't stacktrace
            return False
        visibleTests = self.model.get_value(testIter, 2)
        isVisible = test in visibleTests
        changed = False
        if newValue and not isVisible:
            visibleTests.append(test)
            changed = True
        elif not newValue and isVisible:
            visibleTests.remove(test)
            changed = True

        if (newValue and len(visibleTests) > 1) or (not newValue and len(visibleTests) > 0):
            self.diag.info("No row visibility change : " + repr(test))
            return changed
        else:
            return self.setVisibility(testIter, newValue)

    def setVisibility(self, iter, newValue):
        oldValue = self.model.get_value(iter, 5)
        if oldValue == newValue:
            return False

        self.model.set_value(iter, 5, newValue)
        return True

    def hasVisibleChildren(self, suite):
        return any((self.isMarkedVisible(test) for test in suite.testcases))

