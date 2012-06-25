
# Generic interface to version control systems. We try to keep it as general as possible.

import gtk, gobject, plugins, custom_widgets, os, datetime, subprocess, shutil
from .. import guiplugins, guiutils, entrycompletion
from ..default_gui import adminactions

vcsClass, vcs, annotateClass = None, None, None
    
# All VCS specific stuff goes in this class. One global instance, "vcs" above
class VersionControlInterface:
    def __init__(self, controlDir, name, warningStates, errorStates, latestRevisionName):
        self.name = name
        self.controlDirName = os.path.basename(controlDir)
        self.program = os.path.basename(controlDir).lower().replace(".", "")
        self.warningStates = warningStates
        self.errorStates = errorStates
        self.latestRevisionName = latestRevisionName
        self.lastMoveInVCS = False
        self.defaultArgs = {}

    def checkInstalled(self):
        self.callProgram("help") # throws if it's not installed

    def isVersionControlled(self, path):
        basicArgs = self.getCmdArgs("status")
        for file in self.getFileNames(path, recursive=True):
            status = self.getFileStatus(basicArgs, file)
            if status != "Unknown" and status != "Ignored":
                return True
        return False

    def getFileStatus(self, basicArgs, file):
        output = self.getProcessResults(basicArgs + [ file ])[1]
        return self.getStateFromStatus(output)
        
    def callProgram(self, cmdName, fileArgs=[], **kwargs):
        return subprocess.call(self.getCmdArgs(cmdName, fileArgs),
                               stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w"), **kwargs)

    def callProgramOnFiles(self, cmdName, fileArg, recursive=False, extraArgs=[], **kwargs):
        basicArgs = self.getCmdArgs(cmdName, extraArgs)
        for fileName in self.getFileNamesForCmd(cmdName, fileArg, recursive):
            self.callProgramWithHandler(fileName, basicArgs + [ fileName ], **kwargs)

    def callProgramWithHandler(self, fileName, args, outputHandler=None, outputHandlerArgs=(), **kwargs):
        retcode, stdout, stderr = self.getProcessResults(args, **kwargs)
        if outputHandler:
            outputHandler(retcode, stdout, stderr, fileName, *outputHandlerArgs)

    def getProcessResults(self, args, **kwargs):
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, **kwargs)
        except OSError:
            raise plugins.TextTestError, "Could not run " + self.name + ": make sure you have it installed locally"

        stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr

    def getFileNamesForCmd(self, cmdName, fileArg, recursive):
        if cmdName == "add" and recursive: # assume VCS adds recursively by default, override for CVS
            return [ fileArg ]
        else:
            return self.getFileNames(fileArg, recursive)

    def getFileNames(self, fileArg, recursive, includeDirs=False):
        if os.path.isfile(fileArg):
            return [ fileArg ]
        elif os.path.isdir(fileArg):
            if includeDirs:
                baseFiles = [ fileArg ]
            else:
                baseFiles = []
            if recursive:
                return baseFiles + self.getFilesFromDirRecursive(fileArg, includeDirs)
            else:
                return baseFiles + self.getFilesFromDir(fileArg)
            
    def getFilesFromDir(self, dirName):
        files = []
        for f in sorted(os.listdir(dirName)):
            fullPath = os.path.join(dirName, f)
            if os.path.isfile(fullPath):
                files.append(fullPath)
        return files

    def getFilesFromDirRecursive(self, dirName, includeDirs):
        allFiles = []
        for root, dirs, files in os.walk(dirName):
            if self.controlDirName in dirs:
                dirs.remove(self.controlDirName)
            toAdd = files
            if includeDirs:
                toAdd += dirs
            for f in toAdd:
                fullPath = os.path.join(root, f)
                allFiles.append(fullPath)
            for dir in dirs:
                fullPath = os.path.join(root, dir)
                if os.path.islink(fullPath):
                    allFiles += self.getFilesFromDirRecursive(fullPath, includeDirs)
                    
        return sorted(allFiles)

    def getProgramArgs(self):
        return [ self.program ]

    def getGraphicalDiffArgs(self, diffProgram):
        return [ diffProgram ] # brittle but general...
    
    def getCmdArgs(self, cmdName, extraArgs=[]):
        return self.getProgramArgs() + [ cmdName ] + self.defaultArgs.get(cmdName, []) + extraArgs 

    def getCombinedRevisionOptions(self, r1, r2):
        return [ "-r", r1, "-r", r2 ] # applies to CVS and Mercurial

    def copyPath(self, oldPath, newPath):
        if os.path.isdir(newPath):
            # After a remove, possibly, or after Mercurial has half-moved...
            for path in os.listdir(oldPath):
                oldSubPath = os.path.join(oldPath, path)
                newSubPath = os.path.join(newPath, path)
                if os.path.isdir(oldSubPath):
                    self.copyPath(oldSubPath, newSubPath)
                else:
                    shutil.copyfile(oldSubPath, newSubPath)
        else:
            plugins.copyPath(oldPath, newPath)
                
    def movePath(self, oldPath, newPath):
        self.lastMoveInVCS = self.isVersionControlled(oldPath)
        if self.lastMoveInVCS:
            if os.path.isdir(oldPath):
                newParent = os.path.dirname(newPath)
                # If it's also a parent of the old directory we don't need to check if it's version-controlled.
                if not oldPath.startswith(newParent) and not self.isVersionControlled(newParent):
                    self.callProgramOnFiles("add", newParent) 
            self._movePath(oldPath, newPath)
        else:
            os.rename(oldPath, newPath)

    def _movePath(self, oldPath, newPath):
        self.callProgram("mv", [ oldPath, newPath ])

    def getMoveSuffix(self):
        if self.lastMoveInVCS:
            return " in " + self.name + " (using '" + self.getMoveCommand() + "')"
        else:
            return ""

    def getMoveCommand(self):
        return self.program + " mv"

class BasicVersionControlDialogGUI(guiplugins.ActionResultDialogGUI):
    recursive = False
    def getTitle(self, includeMnemonics=False, adjectiveAfter=True):
        title = self._getTitle()
        if self.recursive or not includeMnemonics:
            title = title.replace("_", "")

        if not includeMnemonics:
            # distinguish these from other actions that may have these names
            title = vcs.name + " " + title
        
        if self.recursive:
            title = self.add_recursion_annotation(title, adjectiveAfter)
        return title

    def add_recursion_annotation(self, title, adjectiveAfter):
        if adjectiveAfter:
            title += " Recursive"
        else:
            title = "Recursive " + title
        return title

    def createDialog(self):
        dialog = guiplugins.ActionResultDialogGUI.createDialog(self)
        dialog.set_name("VCS " + self._getTitle().replace("_", "") + " Window")
        return dialog

    def getDialogTitle(self):
        return self.getTitle(adjectiveAfter=False) + " for the selected files"
            
    def getTooltip(self):
        from copy import copy
        return copy(self.getDialogTitle()).replace(vcs.name, "version control").lower()


# Base class for all version control actions.
class VersionControlDialogGUI(BasicVersionControlDialogGUI):
    def __init__(self, allApps=[], dynamic=False, inputOptions={}):
        BasicVersionControlDialogGUI.__init__(self, allApps)
        self.cmdName = self._getTitle().replace("_", "").lower()
        self.dynamic = dynamic
        self.needsAttention = False
        self.notInRepository = False
    
    def showWarning(self):
        return self.notInRepository or self.needsAttention

    def getResultDialogIconType(self):
        if self.showWarning():
            return gtk.STOCK_DIALOG_WARNING
        else:
            return gtk.STOCK_DIALOG_INFO

    def getExtraArgs(self):
        return []
    
    def getFullResultTitle(self):
        return self.getResultTitle()
    
    def getResultDialogMessage(self):
        message = vcs.name + " " + self.getFullResultTitle() + " shown below."
        if self.needsAttention:
            message += "\n" + vcs.name + " " + self.getResultTitle() + " found files which are not up-to-date or which have conflicts"
        if self.notInRepository:
            message += "\nSome files/directories were not under " + vcs.name + " control."
        cmdArgs = vcs.getCmdArgs(self.cmdName, self.getExtraArgs())
        message += "\n" + vcs.name + " command used: " + " ".join(cmdArgs)
        if not self.recursive:
            message += "\nSubdirectories were ignored, use " + self.getTitle() + " Recursive to get the " + self.getResultTitle() + " for all subdirectories."
        return message
            
    def extraResultDialogWidgets(self):
        all = ["log", "status", "diff", "annotate" ]
        if self.cmdName in all:
            all.remove(self.cmdName)
        return all
            
    def commandHadError(self, retcode, stderr):
        return retcode

    def outputIsInteresting(self, stdout):
        return True

    def getResultTitle(self):
        return self._getTitle().replace("_", "").lower()

    def runAndParse(self):
        self.notInRepository = False
        self.needsAttention = False
        extraArgs = self.getExtraArgs()
        for test, fileArg in self.getFilesForCmd():
            vcs.callProgramOnFiles(self.cmdName, fileArg, self.recursive, extraArgs,
                                   outputHandler=self.handleVcsOutput, outputHandlerArgs=(test,))
                    
    def handleVcsOutput(self, retcode, stdout, stderr, fileName, test):
        if self.commandHadError(retcode, stderr):
            self.notInRepository = True
            self.storeResult(fileName, stderr, test)
        elif self.outputIsInteresting(stdout):
            self.storeResult(fileName, stdout, test)

    def storeResult(self, fileName, output, test):
        info = self.parseOutput(output)
        self.fileToTest[fileName] = test
        self.pages.append((fileName, output, info))
        dirName, local = os.path.split(fileName)
        self.notify("Status", "Analyzing " + self.getResultTitle() + " for " + local + " in test " + os.path.basename(dirName))
        self.notify("ActionProgress", "")
                        
    def parseOutput(self, output):
        return ""
    
    def updateSelection(self, *args):
        newActive = BasicVersionControlDialogGUI.updateSelection(self, *args)
        if not self.dynamic: # See bugzilla 17653
            self.currFileSelection = []
        return newActive
    def notifyNewFileSelection(self, files):
        self.updateFileSelection(files)
    def isActiveOnCurrent(self, *args):
        return len(self.currTestSelection) > 0 
    def messageAfterPerform(self):
        return "Performed " + self.getTooltip() + "."
    def getResultDialogTwoColumnsInTreeView(self):
        return False
    def getResultDialogSecondColumnTitle(self):
        return "Information"
    def getSelectedFile(self):
        return self.filteredTreeModel.get_value(self.treeView.get_selection().get_selected()[1], 3)
    def viewStatus(self, button):
        file = self.getSelectedFile()
        self.diag.info("Viewing status on file " + file)
        status = StatusGUI()
        status.notifyTopWindow(self.topWindow)
        status.currTestSelection = [ self.fileToTest[file] ]
        status.currFileSelection = [ (file, None) ]
        status.performOnCurrent()

    def viewLog(self, button):
        file = self.getSelectedFile()
        logger = LogGUI(self.validApps, self.dynamic)
        logger.topWindow = self.topWindow
        logger.currTestSelection = [ self.fileToTest[file] ]
        logger.currFileSelection = [ (file, None) ]
        logger.performOnCurrent()

    def viewAnnotations(self, button):
        file = self.getSelectedFile()
        annotater = annotateClass()
        annotater.topWindow = self.topWindow
        annotater.currTestSelection = [ self.fileToTest[file] ]
        annotater.currFileSelection = [ (file, None) ]
        annotater.performOnCurrent()

    def viewDiffs(self, button):
        file = self.getSelectedFile()
        differ = DiffGUI()
        differ.topWindow = self.topWindow
        differ.setRevisions(self.revision1.get_text(), self.revision2.get_text())
        differ.currTestSelection = [ self.fileToTest[file] ]
        differ.currFileSelection = [ (file, None) ]
        differ.performOnCurrent()

    def viewGraphicalDiff(self, button):
        path = self.filteredTreeModel.get_value(self.treeView.get_selection().get_selected()[1], 3)
        pathStem = os.path.basename(path).split(".")[0]
        diffProgram = guiutils.guiConfig.getCompositeValue("diff_program", pathStem)
        revOptions = self.getExtraArgs()
        graphDiffArgs = vcs.getGraphicalDiffArgs(diffProgram)
        try:
            if not graphDiffArgs[0] == diffProgram:
                subprocess.call([ diffProgram, "--help" ], stderr=open(os.devnull, "w"), stdout=open(os.devnull, "w"))
            cmdArgs = graphDiffArgs + revOptions + [ path ]
            guiplugins.processMonitor.startProcess(cmdArgs, description="Graphical " + vcs.name + " diff for file " + path,
                                                   exitHandler = self.diffingComplete,
                                                   stderr=open(os.devnull, "w"), stdout=open(os.devnull, "w"))
        except OSError:
            self.showErrorDialog("\nCannot find graphical " + vcs.name + " difference program '" + diffProgram + \
                                     "'.\nPlease install it somewhere on your $PATH.\n")
    
    def diffingComplete(self, *args):
        self.applicationEvent("the version-control graphical diff program to terminate")
                                
    def getRootPath(self):
        appPath = self.currTestSelection[0].app.getDirectory()
        return os.path.split(appPath.rstrip(os.sep))[0]
    
    def getFilesForCmd(self):
        if len(self.currTestSelection) == 0:
            return []
        elif len(self.currFileSelection) > 0:
            return [ (self.currTestSelection[0], f) for (f, comp) in self.currFileSelection ]
        else:
            testLists = [ self.getFilesForCmdForTest(test) for test in self.currTestSelection ]
            return sum(testLists, [])

    def getFilesForCmdForTest(self, test):
        testPath = test.getDirectory()
        if self.dynamic:
            files = sorted([ fileComp.stdFile for fileComp in self.getComparisons(test) ])
            return [ (test, f) for f in files ]
        else:
            return [ (test, testPath) ]

    def getComparisons(self, test):
        try:
            # Leave out new ones
            return test.state.changedResults + test.state.correctResults + test.state.missingResults
        except AttributeError:
            raise plugins.TextTestError, "Cannot establish which files should be compared as no comparison information exists.\n" + \
                  "To create this information, perform 'recompute status' (press '" + \
                         guiutils.guiConfig.getCompositeValue("gui_accelerators", "recompute_status") + "') and try again."

    def isModal(self):
        return False
    
    def addContents(self):
        self.pages = []
        self.fileToTest = {}
        self.runAndParse() # will write to the above two structures
        self.vbox = gtk.VBox()
        self.addExtraWidgets()
        self.addHeader()
        self.addTreeView()
        
    def addExtraWidgets(self):
        self.extraWidgetArea = gtk.HBox()
        self.extraButtonArea = gtk.HButtonBox()
        self.extraWidgetArea.pack_start(self.extraButtonArea, expand=False, fill=False)        
        if len(self.pages) > 0:
            padding = gtk.Alignment()
            padding.set_padding(3, 3, 3, 3)
            padding.add(self.extraWidgetArea)
            self.dialog.vbox.pack_end(padding, expand=False, fill=False)
            extraWidgetsToShow = self.extraResultDialogWidgets()
            if "status" in extraWidgetsToShow:
                self.addStatusWidget()
            if "log" in extraWidgetsToShow:
                self.addLogWidget()
            if "annotate" in extraWidgetsToShow:
                self.addAnnotateWidget()
            if "graphical_diff" in extraWidgetsToShow:
                self.addGraphicalDiffWidget()
            if "diff" in extraWidgetsToShow:
                self.addDiffWidget()

    def addStatusWidget(self):
        button = gtk.Button("_Status")
        button.connect("clicked", self.viewStatus)
        self.extraButtonArea.pack_start(button, expand=False, fill=False)        

    def addLogWidget(self):
        button = gtk.Button("_Log")
        button.connect("clicked", self.viewLog)
        self.extraButtonArea.pack_start(button, expand=False, fill=False)        

    def addAnnotateWidget(self):
        button = gtk.Button("_Annotate")
        button.connect("clicked", self.viewAnnotations)
        self.extraButtonArea.pack_start(button, expand=False, fill=False)        

    def addDiffWidget(self):
        diffButton = gtk.Button("_Differences")
        label1 = gtk.Label(" between revisions ")
        label2 = gtk.Label(" and ")
        self.revision1 = gtk.Entry()
        self.revision1.set_name("Revision 1")
        entrycompletion.manager.register(self.revision1)
        self.revision1.set_text(vcs.latestRevisionName)
        self.revision2 = gtk.Entry()
        self.revision2.set_name("Revision 2")
        entrycompletion.manager.register(self.revision2)
        self.revision1.set_alignment(1.0)
        self.revision2.set_alignment(1.0)
        self.revision1.set_width_chars(6)
        self.revision2.set_width_chars(6)
        self.extraButtonArea.pack_start(diffButton, expand=False, fill=False)
        self.extraWidgetArea.pack_start(label1, expand=False, fill=False)
        self.extraWidgetArea.pack_start(self.revision1, expand=False, fill=False)
        self.extraWidgetArea.pack_start(label2, expand=False, fill=False)
        self.extraWidgetArea.pack_start(self.revision2, expand=False, fill=False)
        diffButton.connect("clicked", self.viewDiffs)

    def addGraphicalDiffWidget(self):
        button = gtk.Button("_Graphical Diffs")
        button.connect("clicked", self.viewGraphicalDiff)
        self.extraButtonArea.pack_start(button, expand=False, fill=False)        

    def addHeader(self):
        message = self.getResultDialogMessage()
        if message:
            hbox = gtk.HBox()
            iconType = self.getResultDialogIconType()
            hbox.pack_start(self.getStockIcon(iconType), expand=False, fill=False)
            hbox.pack_start(gtk.Label(message), expand=False, fill=False)        
            alignment = gtk.Alignment()
            alignment.set(0.0, 1.0, 1.0, 1.0)
            alignment.set_padding(5, 5, 0, 5)
            alignment.add(hbox)
            self.vbox.pack_start(alignment, expand=False, fill=False)

    def getStockIcon(self, stockItem):
        imageBox = gtk.VBox()
        imageBox.pack_start(gtk.image_new_from_stock(stockItem, gtk.ICON_SIZE_DIALOG), expand=False)
        return imageBox

    def addTreeView(self):
        hpaned = gtk.HPaned()
        hpaned.set_name("VCS dialog separator") # Mostly so we can filter the proportions, which we don't set

        # We need buffer when creating treeview, so create right-hand side first ...
        self.textBuffer = gtk.TextBuffer()
        textView = gtk.TextView(self.textBuffer)
        textView.set_editable(False)
        textView.set_name("VCS Output View")
        window2 = gtk.ScrolledWindow()
        window2.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        window2.add(textView)
        hpaned.pack2(window2, True, True)

        self.createTreeView()
        window1 = gtk.ScrolledWindow()
        window1.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        window1.add(self.treeView)
        hpaned.pack1(window1, False, True)

        if len(self.pages) > 0:
            parentSize = self.topWindow.get_size()
            self.dialog.resize(parentSize[0], int(parentSize[0] / 1.5))
            self.vbox.pack_start(hpaned, expand=True, fill=True)
        self.dialog.vbox.pack_start(self.vbox, expand=True, fill=True)
                
    def createTreeView(self):
        # Columns are: 0 - Tree node name
        #              1 - Content (output from VCS) for the corresponding file
        #              2 - Info. If the plugin wants to show two columns, this
        #                  is shown in the second column. If not it should be empty.
        #              3 - Full path to the file corresponding to the node
        #              4 - Should the row be visible?
        self.treeModel = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING,
                                       gobject.TYPE_STRING, gobject.TYPE_STRING,
                                       gobject.TYPE_BOOLEAN)
        self.filteredTreeModel = self.treeModel.filter_new()
        self.filteredTreeModel.set_visible_column(4)
        if len(self.currTestSelection) > 0:
            rootDir = self.getRootPath()
        
        fileToIter = {}
        for fileName, content, info in self.pages:
            label = plugins.relpath(fileName, rootDir)
            self.diag.info("Adding info for file " + label)
            utfContent = guiutils.convertToUtf8(content)
            path = label.split(os.sep)
            currentFile = rootDir
            prevIter = None
            for element in path:
                currentFile = os.path.join(currentFile, element)
                currentInfo = ""
                currentElement = element.strip(" \n")
                if currentFile == fileName:
                    currentInfo = info
                else:
                    currentElement = "<span weight='bold'>" + currentElement + "</span>"
                currIter = fileToIter.get(currentFile)
                if currIter is None:
                    newRow = (currentElement, utfContent, currentInfo, currentFile, True)
                    currIter = self.treeModel.append(prevIter, newRow)
                    fileToIter[currentFile] = currIter
                prevIter = currIter
                        
        self.treeView = gtk.TreeView(self.filteredTreeModel)
        self.treeView.set_name("VCS " + self.cmdName + " info tree")
        self.treeView.set_enable_search(False)
        fileRenderer = gtk.CellRendererText()
        fileColumn = gtk.TreeViewColumn("File", fileRenderer, markup=0)
        fileColumn.set_resizable(True)
        self.treeView.append_column(fileColumn)
        self.treeView.set_expander_column(fileColumn)
        if self.getResultDialogTwoColumnsInTreeView():
            infoRenderer = gtk.CellRendererText()
            self.infoColumn = custom_widgets.ButtonedTreeViewColumn(self.getResultDialogSecondColumnTitle(), infoRenderer, markup=2)
            self.infoColumn.set_resizable(True)
            self.treeView.append_column(self.infoColumn)
        self.treeView.get_selection().set_select_function(self.canSelect)
        self.treeView.expand_all()

        if len(self.pages) > 0:
            firstFile = self.pages[0][0]
            firstIter = self.filteredTreeModel.convert_child_iter_to_iter(fileToIter[firstFile])
            self.updateForIter(firstIter)
            self.treeView.get_selection().select_iter(firstIter)

        self.treeView.get_selection().connect("changed", self.showOutput)
        
    def updateForIter(self, iter):
        self.extraWidgetArea.set_sensitive(True)
        text = self.filteredTreeModel.get_value(iter, 1)
        self.textBuffer.set_text(text)
        return text
        
    def showOutput(self, selection):
        model, iter = selection.get_selected()
        if iter:
            self.updateForIter(iter)
        else:
            self.extraWidgetArea.set_sensitive(False)

    def canSelect(self, path):
        return not self.treeModel.iter_has_child(
            self.treeModel.get_iter(self.filteredTreeModel.convert_path_to_child_path(path)))


#
# 1 - First the methods which just check the repository and checked out files.
#


class LogGUI(VersionControlDialogGUI):
    def _getTitle(self):
        return "_Log"
    def getResultTitle(self):
        return "logs"
    def getResultDialogTwoColumnsInTreeView(self):
        return True
    def getResultDialogSecondColumnTitle(self):
        return "Last revision committed (UTC)"
        
    def parseOutput(self, output):
        then = vcs.getDateFromLog(output)
        if then is None:
            return "Not in " + vcs.name

        now = datetime.datetime.utcnow()
        return self.getTimeDifference(now, then)

    # Show a human readable time difference string. Diffs larger than farAwayLimit are
    # written as the actual 'to' time, while other diffs are written e.g. 'X days ago'.
    # If markup is True, diffs less than closeLimit are boldified and diffs the same
    # day are red as well.
    def getTimeDifference(self, now, then, markup = True, \
                          closeLimit = datetime.timedelta(days=3), \
                          farAwayLimit = datetime.timedelta(days=7)):
        difference = now - then # Assume this is positive ...
        if difference > farAwayLimit:
            return then.ctime()

        stringDiff = str(difference.days) + " days ago"
        yesterday = now - datetime.timedelta(days=1)
        if now.day == then.day:
            stringDiff = "Today at " + then.strftime("%H:%M:%S")
            if markup:
                stringDiff = "<span weight='bold' foreground='red'>" + stringDiff + "</span>"
        elif yesterday.day == then.day and yesterday.month == then.month and yesterday.year == then.year:
            stringDiff = "Yesterday at " + then.strftime("%H:%M:%S")
            if markup:
                stringDiff = "<span weight='bold'>" + stringDiff + "</span>"
        elif difference <= closeLimit and markup:
            stringDiff = "<span weight='bold'>" + stringDiff + "</span>"
        return stringDiff     


class DiffGUI(VersionControlDialogGUI):
    def __init__(self, *args):
        VersionControlDialogGUI.__init__(self, *args)
        self.cmdName = "diff"
        self.revision1 = ""
        self.revision2 = ""
    def setRevisions(self, rev1, rev2):
        self.revision1 = rev1
        self.revision2 = rev2
    def _getTitle(self):
        return "_Difference"
    def getResultTitle(self):
        return "differences"
    def getResultDialogMessage(self):
        if len(self.pages) == 0:
            return "All files are up-to-date and unmodified compared to the latest repository version."
        else:
            return VersionControlDialogGUI.getResultDialogMessage(self)

    def getFullResultTitle(self):
        return "differences " + self.getRevisionMessage()
    def showWarning(self):
        return len(self.pages) > 0
    def commandHadError(self, retcode, stderr):
        # Diff returns an error code for differences, not just for errors
        return retcode and len(stderr) > 0
    def outputIsInteresting(self, stdout):
        # Don't show diffs if they're empty
        return len(stdout) > 0
    def getRevisionMessage(self):
        if self.revision1 == "" and self.revision2 == "":
            return "compared to the latest revision"
        elif self.revision1 == "":
            return "between the local file and revision " + self.revision2
        elif self.revision2 == "":
            return "between revision " + self.revision1 + " and the local file"
        else:
            return "between revisions " + self.revision1 + " and " + self.revision2

    def getExtraArgs(self):
        if self.revision1 and self.revision2:
            return vcs.getCombinedRevisionOptions(self.revision1, self.revision2)
        elif self.revision1:
            return [ "-r", self.revision1 ]
        elif self.revision2:
            return [ "-r", self.revision2 ]
        else:
            return []

    def extraResultDialogWidgets(self):
        return VersionControlDialogGUI.extraResultDialogWidgets(self) + ["graphical_diff"]

        
class StatusGUI(VersionControlDialogGUI):
    def __init__(self, *args):
        VersionControlDialogGUI.__init__(self, *args)
        self.popupMenu = None
    
    def _getTitle(self):
        return "_Status"
    
    def getResultDialogTwoColumnsInTreeView(self):
        return True
    
    def getStatusMarkup(self, status):
        if status in vcs.warningStates:
            return "<span weight='bold'>" + status + "</span>"
        elif status in vcs.errorStates:
            return "<span weight='bold' foreground='red'>" + status + "</span>"
        else:
            return status
 
    def parseOutput(self, output):
        status = vcs.getStateFromStatus(output)
        if status == "Unknown":
            self.notInRepository = True
        elif status in vcs.errorStates:
            self.needsAttention = True
        return self.getStatusMarkup(status)
            
    def createPopupMenu(self):
        # Each unique info column (column 2) gets its own menu item in the popup menu
        uniqueInfos = []
        self.treeModel.foreach(self.collectInfos, uniqueInfos)

        menu = gtk.Menu()
        for info in uniqueInfos:
            menuItem = gtk.CheckMenuItem(info)
            menuItem.set_active(True)
            menuItem.set_name(info)
            menu.append(menuItem)
            menuItem.connect("toggled", self.toggleVisibility)         
            menuItem.show()
        return menu

    def toggleVisibility(self, menuItem):
        self.treeModel.foreach(self.setVisibility, (menuItem.get_name(), menuItem.get_active()))
        self.treeView.expand_row(self.filteredTreeModel.get_path(self.filteredTreeModel.get_iter_root()), True)
        
    def getStatus(self, iter):
        markedUpStatus = self.treeModel.get_value(iter, 2)
        start = markedUpStatus.find(">")
        if start == -1:
            return markedUpStatus
        else:
            end = markedUpStatus.rfind("<")
            return markedUpStatus[start + 1:end]
    
    def setVisibility(self, model, path, iter, (actionName, actionState)):
        if model.iter_parent(iter) is not None and (actionName == "" or self.getStatus(iter) == actionName):
            model.set_value(iter, 4, actionState)
            parentIter = model.iter_parent(iter)
            if actionState or self.hasNoVisibleChildren(model, parentIter):
                self.setVisibility(model, model.get_path(parentIter), parentIter, ("", actionState))
        
    def hasNoVisibleChildren(self, model, iter):
        i = model.iter_children(iter)
        while i:
            if model.get_value(i, 4):
                return False
            i = model.iter_next(i)
        return True
        
    def collectInfos(self, model, path, iter, infos):
        info = model.get_value(iter, 2)
        if info != "":
            rawInfo = info.replace("<span weight='bold'>", "").replace("<span weight='bold' foreground='red'>",
                                                                       "").replace("</span>", "").strip()
            if rawInfo not in infos:
                infos.append(rawInfo)
                    
    def addContents(self):
        VersionControlDialogGUI.addContents(self)
        self.popupMenu = self.createPopupMenu()
        self.infoColumn.set_clickable(True)
        self.infoColumn.get_button().connect("button-press-event", self.showPopupMenu)
        self.treeView.grab_focus() # Or the column button gets focus ...
        
    def showPopupMenu(self, button, event):
        if event.button == 3: 
            self.popupMenu.popup(None, None, None, event.button, event.time)
            

class AnnotateGUI(VersionControlDialogGUI):
    def _getTitle(self):
        return "A_nnotate"
    def getResultTitle(self):
        return "annotations"


class UpdateGUI(BasicVersionControlDialogGUI):
    def _getTitle(self):
        return "Update"

    def getSignalsSent(self):
        return [ "Refresh" ]

    def addContents(self):
        args = vcs.getCmdArgs("update")
        retcode, stdout, stderr = vcs.getProcessResults(args, cwd=self.currTestSelection[0].app.getDirectory())
        buffer = gtk.TextBuffer()
        buffer.set_text(stdout + stderr)
        textView = gtk.TextView(buffer)
        self.dialog.vbox.pack_start(textView, expand=True, fill=True)
        self.notify("Refresh")


class AddGUI(VersionControlDialogGUI):
    def _getTitle(self):
        return "A_dd"
    def getResultDialogMessage(self):
        message = "Output from '" + vcs.name + " add' shown below."
        if not self.recursive:
            message += "\nSubdirectories were ignored, use " + self.getTitle() + " Recursive to add the files from all subdirectories."
        return message
    def commandHadError(self, retcode, stderr):
        # Particularly CVS likes to write add output on stderr for some reason...
        return len(stderr) > 0

class VcsAdminAction:
    @staticmethod
    def removePath(*args):
        return vcs.removePath(*args)

    @staticmethod
    def movePath(*args):
        return vcs.movePath(*args)

    @staticmethod
    def copyPath(*args):
        return vcs.copyPath(*args)


class VcsRemoveAction(VcsAdminAction):
    def getFileRemoveWarning(self):
        return "Any " + vcs.name + "-controlled files will be removed in " + vcs.name + ".\n" + \
               "Any files that are not version controlled will be removed from the file system and hence may not be recoverable."


class RemoveTests(VcsRemoveAction, adminactions.RemoveTests):
    pass

class RemoveFiles(VcsRemoveAction, adminactions.RemoveFiles):
    pass

class RemoveTestsForPopup(VcsRemoveAction, adminactions.RemoveTestsForPopup):
    pass
    
    
class RenameTest(VcsAdminAction, adminactions.RenameTest):
    def getNameChangeMessage(self, newName):
        origMessage = adminactions.RenameTest.getNameChangeMessage(self, newName)
        return origMessage + vcs.getMoveSuffix() 

class RenameFile(VcsAdminAction, adminactions.RenameFile):
    def getNameChangeMessage(self, newName):
        origMessage = adminactions.RenameFile.getNameChangeMessage(self, newName)
        return origMessage + vcs.getMoveSuffix() 


class PasteTests(VcsAdminAction, adminactions.PasteTests):
    def getStatusMessage(self, *args):
        origMessage = adminactions.PasteTests.getStatusMessage(self, *args)
        if self.removeAfter:
            return origMessage + vcs.getMoveSuffix()
        else:
            return origMessage

            
class LogGUIRecursive(LogGUI):
    recursive = True

class DiffGUIRecursive(DiffGUI):
    recursive = True

class StatusGUIRecursive(StatusGUI):
    recursive = True
        
class AnnotateGUIRecursive(AnnotateGUI):
    recursive = True    

class AddGUIRecursive(AddGUI):
    recursive = True

#
# Configuration for the Interactive Actions
#
class InteractiveActionConfig(guiplugins.InteractiveActionConfig):
    def __init__(self, controlDir):
        global vcs, annotateClass
        vcs = vcsClass(controlDir)
        annotateClass = self.annotateClasses()[0]

    def getMenuNames(self):
        return [ vcs.name ]

    def getInteractiveActionClasses(self, dynamic):
        return [ LogGUI, LogGUIRecursive, DiffGUI, DiffGUIRecursive, StatusGUI, StatusGUIRecursive ] +\
               self.annotateClasses() + [ AddGUI, AddGUIRecursive, UpdateGUI ]

    def annotateClasses(self):
        return [ AnnotateGUI, AnnotateGUIRecursive ]

    def getRenameTestClass(self):
        return RenameTest

    def getReplacements(self):
        return { adminactions.RemoveTests : RemoveTests,
                 adminactions.RemoveFiles : RemoveFiles,
                 adminactions.RemoveTestsForPopup : RemoveTestsForPopup,
                 adminactions.RenameTest  : self.getRenameTestClass(),
                 adminactions.RenameFile  : RenameFile,
                 adminactions.PasteTests  : PasteTests }
