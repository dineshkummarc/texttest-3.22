
"""
All the actions for administering the files and directories in a test suite
"""

import gtk, plugins, os, shutil
from .. import guiplugins, guiutils
from ordereddict import OrderedDict

# Cut, copy and paste
class FocusDependentAction(guiplugins.ActionGUI):
    def notifyTopWindow(self, window):
        guiplugins.ActionGUI.notifyTopWindow(self, window)
        window.connect("set-focus", self.focusChanged)

    def focusChanged(self, dummy, widget):
        freeTextWidget = isinstance(widget, gtk.Entry) or isinstance(widget, gtk.TextView)
        if freeTextWidget:
            self.setSensitivity(False)
        elif self.isActiveOnCurrent():
            self.setSensitivity(True)

class ClipboardAction(FocusDependentAction):
    def isActiveOnCurrent(self, *args):
        if guiplugins.ActionGUI.isActiveOnCurrent(self, *args):
            for test in self.currTestSelection:
                if test.parent:
                    return True
        return False

    def getSignalsSent(self):
        return [ "Clipboard" ]

    def _getStockId(self):
        return self.getName()

    def _getTitle(self):
        return "_" + self.getName().capitalize()

    def getTooltip(self):
        return self.getName().capitalize() + " selected tests"

    def noAncestorsSelected(self, test):
        if not test.parent:
            return True
        if test.parent in self.currTestSelection:
            return False
        else:
            return self.noAncestorsSelected(test.parent)
        
    def performOnCurrent(self):
        # If suites are selected, don't also select their contents
        testsForClipboard = filter(self.noAncestorsSelected, self.currTestSelection)
        self.notify("Clipboard", testsForClipboard, cut=self.shouldCut())


class CopyTests(ClipboardAction):
    def getName(self):
        return "copy"
    def shouldCut(self):
        return False

class CutTests(ClipboardAction):
    def getName(self):
        return "cut"
    def shouldCut(self):
        return True

class PasteTests(FocusDependentAction):
    def __init__(self, *args):
        FocusDependentAction.__init__(self, *args)
        self.clipboardTests = []
        self.removeAfter = False
    def singleTestOnly(self):
        return True
    def _getStockId(self):
        return "paste"
    def _getTitle(self):
        return "_Paste"
    def getTooltip(self):
        return "Paste tests from clipboard"
    def notifyClipboard(self, tests, cut=False):
        self.clipboardTests = tests
        self.removeAfter = cut
        self.setSensitivity(True)

    def isActiveOnCurrent(self, test=None, state=None):
        return guiplugins.ActionGUI.isActiveOnCurrent(self, test, state) and len(self.clipboardTests) > 0

    def getCurrentTestMatchingApp(self, test):
        for currTest in self.currTestSelection:
            if currTest.app == test.app:
                return currTest

    def getDestinationInfo(self, test):
        currTest = self.getCurrentTestMatchingApp(test)
        if currTest is None:
            return None, 0
        if currTest.classId() == "test-suite" and currTest not in self.clipboardTests:
            return currTest, 0
        else:
            return currTest.parent, currTest.positionInParent() + 1

    def getNewTestName(self, suite, oldName):
        existingTest = suite.findSubtest(oldName)
        if not existingTest:
            dirName = suite.getNewDirectoryName(oldName)
            if not os.path.exists(dirName):
                return oldName
        elif self.willBeRemoved(existingTest):
            return oldName
        
        nextNameCandidate = self.findNextNameCandidate(oldName)
        return self.getNewTestName(suite, nextNameCandidate)
    
    def willBeRemoved(self, test):
        return self.removeAfter and test in self.clipboardTests

    def findNextNameCandidate(self, name):
        copyPos = name.find("_copy_")
        if copyPos != -1:
            copyEndPos = copyPos + 6
            number = int(name[copyEndPos:])
            return name[:copyEndPos] + str(number + 1)
        elif name.endswith("copy"):
            return name + "_2"
        else:
            return name + "_copy"

    def getNewDescription(self, test):
        if len(test.description) or self.removeAfter:
            return test.description
        else:
            return "Copy of " + test.name

    def getRepositionPlacement(self, test, placement):
        currPos = test.positionInParent()
        if placement > currPos:
            return placement - 1
        else:
            return placement

    def messageAfterPerform(self):
        pass # do it below...
        
    def performOnCurrent(self):
        newTests = []
        destInfo = OrderedDict()
        for test in self.clipboardTests:
            suite, placement = self.getDestinationInfo(test)
            if suite:
                newName = self.getNewTestName(suite, test.name)
                destInfo[test] = suite, placement, newName
        if len(destInfo) == 0:
            raise plugins.TextTestError, "Cannot paste test there, as the copied test and currently selected test have no application/version in common"

        suiteDeltas = {} # When we insert as we go along, need to update subsequent placements
        for test, (suite, placement, newName) in destInfo.items():
            suiteDeltas.setdefault(suite, 0)
            realPlacement = placement + suiteDeltas.get(suite)
            if self.removeAfter and newName == test.name and suite is test.parent:
                # Cut + paste to the same suite is basically a reposition, do it as one action
                repositionPlacement = self.getRepositionPlacement(test, realPlacement)
                plugins.tryFileChange(test.parent.repositionTest, "Failed to reposition test: no permissions to edit the testsuite file",
                                      test, repositionPlacement)
                newTests.append(test)
            else:
                newDesc = self.getNewDescription(test)
                # Create test files first, so that if it fails due to e.g. full disk, we won't register the test either...
                testDir = suite.getNewDirectoryName(newName)
                try:
                    self.moveOrCopy(test, testDir)
                    suite.registerTest(newName, newDesc, realPlacement)
                    testImported = suite.addTest(test.__class__, os.path.basename(testDir), newDesc, realPlacement)
                    # "testImported" might in fact be a suite: in which case we should read all the new subtests which
                    # might have also been copied
                    testImported.readContents(initial=False)
                    testImported.updateAllRelPaths(test.getRelPath())
                    suiteDeltas[suite] += 1
                    newTests.append(testImported)
                    if self.removeAfter:
                        message = "Failed to remove old test: didn't have sufficient write permission to the test files. Test copied instead of moved."
                        plugins.tryFileChange(test.remove, message)
                except EnvironmentError, e:
                    if os.path.isdir(testDir):
                        shutil.rmtree(testDir)
                    self.showErrorDialog("Failed to paste test:\n" + str(e))
                    
        self.notify("SetTestSelection", newTests)
        self.currTestSelection = newTests
        self.notify("Status", self.getStatusMessage(suiteDeltas))
        if self.removeAfter:
            # After a paste from cut, subsequent pastes should behave like copies of the new tests
            self.notify("Clipboard", newTests, cut=False)
            self.clipboardTests = newTests
            self.removeAfter = False
        for suite, placement, newName in destInfo.values():
            suite.contentChanged()

    def getStatusMessage(self, suiteDeltas):
        suiteName = suiteDeltas.keys()[0].name
        if self.removeAfter:
            return "Moved " + self.describeTests() + " to suite '" + suiteName + "'"
        else:
            return "Pasted " +  self.describeTests() + " to suite '" + suiteName + "'"

    def getSignalsSent(self):
        return [ "SetTestSelection", "Clipboard" ]

    def moveOrCopy(self, test, newDirName):
        # If it exists it's because a previous copy has already taken across the directory
        if not os.path.isdir(newDirName):
            oldDirName = test.getDirectory()
            if self.removeAfter:
                self.movePath(oldDirName, newDirName)
            else:
                self.copyPath(oldDirName, newDirName)

    # Methods overridden by version control
    @staticmethod
    def movePath(oldDirName, newDirName):
        os.rename(oldDirName, newDirName)

    @staticmethod
    def copyPath(oldDirName, newDirName):
        shutil.copytree(oldDirName, newDirName)
    


# And a generic import test. Note acts on test suites
class ImportTest(guiplugins.ActionDialogGUI):
    def __init__(self, *args):
        guiplugins.ActionDialogGUI.__init__(self, *args)
        self.optionGroup.addOption("name", self.getNameTitle())
        self.optionGroup.addOption("desc", self.getDescTitle(), description="Enter a description of the new " + self.testType().lower() + " which will be inserted as a comment in the testsuite file.", multilineEntry=True)
        self.optionGroup.addOption("testpos", self.getPlaceTitle(), "last in suite", allocateNofValues=2, description="Where in the test suite should the test be placed?")
        self.testsImported = []

    def getConfirmationMessage(self):
        testName = self.getNewTestName()
        suite = self.getDestinationSuite()
        self.checkName(suite, testName)
        newDir = os.path.join(suite.getDirectory(), testName)
        if os.path.isdir(newDir):
            if self.testFilesExist(newDir, suite.app):
                raise plugins.TextTestError, "Test already exists for application " + suite.app.fullName() + \
                          " : " + os.path.basename(newDir)
            else:
                return "Test directory already exists for '" + testName + "'\nAre you sure you want to use this name?"
        else:
            return ""

    def _getStockId(self):
        return "add"
    
    def getSizeAsWindowFraction(self):
        # size of the dialog
        return 0.5, 0.45

    def testFilesExist(self, dir, app):
        for fileName in os.listdir(dir):
            parts = fileName.split(".")
            if len(parts) > 1 and parts[1] == app.name:
                return True
        return False

    def singleTestOnly(self):
        return True

    def correctTestClass(self):
        return "test-suite"

    def getNameTitle(self):
        return self.testType() + " Name"

    def getDescTitle(self):
        return self.testType() + " Description"

    def getPlaceTitle(self):
        return "\nPlace " + self.testType()

    def getDefaultName(self):
        return ""

    def getDefaultDesc(self):
        return ""
    
    def updateOptions(self):
        self.optionGroup.setOptionValue("name", self.getDefaultName())
        self.optionGroup.setOptionValue("desc", self.getDefaultDesc())
        self.setPlacements(self.currTestSelection[0])
        return True

    def setPlacements(self, suite):
        # Add suite and its children
        placements = [ "first in suite" ]
        for test in suite.testcases:
            placements += [ "after " + test.name ]
        placements.append("last in suite")

        self.optionGroup.setPossibleValues("testpos", placements)
        self.optionGroup.getOption("testpos").reset()

    def _getTitle(self):
        return "Add " + self.testType()

    def testType(self): #pragma : no cover - doc only
        return ""

    def messageAfterPerform(self):
        if len(self.testsImported):
            return "Added new " + ", ".join((repr(test) for test in self.testsImported))

    def getNewTestName(self):
        # Overwritten in subclasses - occasionally it can be inferred
        return self.optionGroup.getOptionValue("name").strip()

    def performOnCurrent(self):
        testName = self.getNewTestName()
        description = self.optionGroup.getOptionValue("desc")
        placement = self.getPlacement()
        self.testsImported = []
        for suite in self.currTestSelection:
            suite.registerTest(testName, description, placement)
            testDir = suite.makeSubDirectory(testName)
            self.testsImported.append(self.createTestContents(suite, testDir, description, placement))
            suite.contentChanged()

        self.notify("SetTestSelection", self.testsImported)

    def getSignalsSent(self):
        return [ "SetTestSelection" ]
    def getDestinationSuite(self):
        return self.currTestSelection[0]
    
    def getPlacement(self):
        option = self.optionGroup.getOption("testpos")
        return option.possibleValues.index(option.getValue())

    def checkName(self, suite, testName):
        if len(testName) == 0:
            raise plugins.TextTestError, "No name given for new " + self.testType() + "!" + "\n" + \
                  "Fill in the 'Adding " + self.testType() + "' tab below."
        if testName.find(" ") != -1:
            raise plugins.TextTestError, "The new " + self.testType() + \
                  " name is not permitted to contain spaces, please specify another"
        for test in suite.testcases:
            if test.name == testName:
                raise plugins.TextTestError, "A " + self.testType() + " with the name '" + \
                      testName + "' already exists, please choose another name"


class ImportTestCase(ImportTest):
    def __init__(self, *args):
        ImportTest.__init__(self, *args)
        self.addDefinitionFileOption()
    def testType(self):
        return "Test"
    def addDefinitionFileOption(self):
        self.addOption("opt", "Command line options")
    def createTestContents(self, suite, testDir, description, placement):
        self.writeDefinitionFiles(suite, testDir)
        self.writeEnvironmentFile(suite, testDir)
        self.writeResultsFiles(suite, testDir)
        return suite.addTestCase(os.path.basename(testDir), description, placement)
    def getWriteFileName(self, name, suite, testDir):
        return os.path.join(testDir, name + "." + suite.app.name)
    def getWriteFile(self, name, suite, testDir):
        return open(self.getWriteFileName(name, suite, testDir), "w")

    def writeEnvironmentFile(self, suite, testDir):
        envDir = self.getEnvironment(suite)
        if len(envDir) == 0:
            return
        envFile = self.getWriteFile("environment", suite, testDir)
        for var, value in envDir.items():
            envFile.write(var + ":" + value + "\n")
        envFile.close()

    def writeDefinitionFiles(self, suite, testDir):
        optionString = self.getOptions(suite)
        if len(optionString):
            optionFile = self.getWriteFile("options", suite, testDir)
            optionFile.write(optionString + "\n")
        return optionString

    def getOptions(self, *args):
        return self.optionGroup.getOptionValue("opt")

    def getEnvironment(self, *args):
        return {}

    def writeResultsFiles(self, suite, testDir):
        # Cannot do anything in general
        pass

class ImportTestSuite(ImportTest):
    def __init__(self, *args):
        ImportTest.__init__(self, *args)
        self.addEnvironmentFileOptions()
    def testType(self):
        return "Suite"
    def createTestContents(self, suite, testDir, description, placement):
        return suite.addTestSuite(os.path.basename(testDir), description, placement, self.writeEnvironmentFiles)
    def addEnvironmentFileOptions(self):
        self.addSwitch("env", "Add environment file")
    def writeEnvironmentFiles(self, newSuite):
        if self.optionGroup.getSwitchValue("env"):
            envFile = os.path.join(newSuite.getDirectory(), "environment")
            file = open(envFile, "w")
            file.write("# Dictionary of environment to variables to set in test suite\n")


class ImportApplication(guiplugins.ActionDialogGUI):
    def __init__(self, allApps, dynamic, inputOptions):
        guiplugins.ActionDialogGUI.__init__(self, allApps, dynamic, inputOptions)
        self.fileChooser = None
        self.rootDirectories = inputOptions.rootDirectories
        self.addOption("name", "Full name of application", description="Name of application to use in reports etc.")
        self.addOption("ext", "\nFile extension to use for TextTest files associated with this application", description="Short space-free extension, to identify all TextTest's files associated with this application")
        possibleSubDirs = self.findSubDirectories()
        self.addOption("subdir", "\nSubdirectory name to store the above application files under (leave blank for local storage)", possibleValues=possibleSubDirs)
        self.addOption("javaclass", "\nJava Class name (instead of executable program)")
        self.addSwitch("gui", "GUI testing option chooser",
                       options = [ "Disable GUI testing options",
                                   "PyGTK GUI with StoryText",
                                   "Tkinter GUI with StoryText",
                                   "wxPython GUI with StoryText",
                                   "SWT GUI with StoryText",
                                   "Eclipse RCP GUI with StoryText",
                                   "Java Swing GUI with StoryText",
                                   "Other embedded Use-case Recorder (e.g. NUseCase)",
                                   "Other GUI-test tool (enable virtual display only)" ],
                       hideOptions=True)

        possibleDirs = []
        for app in allApps:
            if app.getDirectory() not in possibleDirs:
                possibleDirs.append(app.getDirectory())
        if len(possibleDirs) == 0:
            possibleDirs = self.rootDirectories
        self.addOption("exec", "\nSelect executable program to test", description="The full path to the program you want to test", possibleDirs=possibleDirs, selectFile=True)
        
    def createFileChooser(self, *args):
        self.fileChooser = guiplugins.ActionDialogGUI.createFileChooser(self, *args)
        return self.fileChooser

    def createOptionWidget(self, option):
        box, entry = guiplugins.ActionDialogGUI.createOptionWidget(self, option)
        if option is self.optionGroup.getOption("javaclass"):
            entry.connect("changed", self.javaClassChanged)
        return box, entry

    def javaClassChanged(self, *args):
        if self.fileChooser:
            self.setFileChooserSensitivity()

    def setFileChooserSensitivity(self):
        javaclass = self.optionGroup.getValue("javaclass")
        sensitive = self.fileChooser.get_property("sensitive")
        newSensitive = len(javaclass) == 0
        if newSensitive != sensitive:
            self.fileChooser.set_property("sensitive", newSensitive)

    def findSubDirectories(self):
        allDirs = []
        for rootDir in self.rootDirectories:
            usableFiles = filter(lambda f: f not in plugins.controlDirNames, os.listdir(rootDir))
            allFiles = [ os.path.join(rootDir, f) for f in usableFiles ]
            allDirs += filter(os.path.isdir, allFiles)
        allDirs.sort()
        return map(os.path.basename, allDirs)

    def notifyAllRead(self):
        if self.noApps:
            self.runInteractive()

    def isActiveOnCurrent(self, *args):
        return True
    def _getStockId(self):
        return "add"
    def _getTitle(self):
        return "Add Application"
    def messageAfterPerform(self):
        pass
    def getTooltip(self):
        return "Define a new tested application"

    def checkSanity(self, ext, executable, subdir, directory, javaClass):
        if not ext:
            raise plugins.TextTestError, "Must provide a file extension for TextTest files"

        for char in " ./":
            if char in ext:
                raise plugins.TextTestError, "File extensions may not contain the character " + repr(char) + ". It's recommended to stick to alphanumeric characters for this field."

        if not javaClass and (not executable or not os.path.isfile(executable)):
            raise plugins.TextTestError, "Must provide a valid path to a program to test"

        for char in "/\\":
            if char in subdir:
                raise plugins.TextTestError, "Subdirectory name must be a local name (not contain " + repr(char) + ").\nTextTest only looks for applications one level down in the hierarchy."

        if os.path.exists(os.path.join(directory, "config." + ext)):
            raise plugins.TextTestError, "Test-application already exists at the indicated location with the indicated extension: please choose another name"

    def getSignalsSent(self):
        return [ "NewApplication" ]

    def performOnCurrent(self):
        executable = self.optionGroup.getOptionValue("exec")
        ext = self.optionGroup.getOptionValue("ext")
        subdir = self.optionGroup.getOptionValue("subdir")
        directory = self.findFullDirectoryPath(subdir)
        javaClass = self.optionGroup.getOptionValue("javaclass")
        self.checkSanity(ext, executable, subdir, directory, javaClass)
        plugins.ensureDirectoryExists(directory)
        if javaClass:
            executable = javaClass
        configEntries = OrderedDict({ "executable" : executable })
        configEntries["filename_convention_scheme"] = "standard"
        if javaClass:
            configEntries["interpreter"] = "java"
        fullName = self.optionGroup.getOptionValue("name")
        if fullName:
            configEntries["full_name"] = fullName
        useGui = self.optionGroup.getSwitchValue("gui")
        if useGui > 0:
            configEntries["use_case_record_mode"] = "GUI"
            if useGui != 8:
                configEntries["slow_motion_replay_speed"] = "3.0"
        if useGui in range(1, 7):
            interpreter = "storytext"
            if useGui == 2:
                interpreter += " -i tkinter"
            elif useGui == 3:
                interpreter += " -i wx"
            elif useGui == 4:
                interpreter += " -i javaswt"
            elif useGui == 5:
                interpreter += " -i javarcp"
            elif useGui == 6:
                interpreter += " -i javaswing"
            configEntries["use_case_recorder"] = "storytext"
            configEntries["interpreter"] = interpreter
            if useGui == 1: # PyGTK
                comment = "XDG_CONFIG_HOME points to user's ~/.config directory.\n" + \
                          "Behaviour of e.g. FileChoosers can vary wildly depending on settings there.\n" + \
                          "The following settings makes sure it uses an empty test-dependent directory instead."
                configEntries["section_comment"] = comment
                configEntries["copy_test_path"] = "xdg_config_home"
                configEntries["test_data_ignore"] = "xdg_config_home"
                configEntries["test_data_environment"] = ("xdg_config_home", "XDG_CONFIG_HOME")
            elif useGui == 2:
                # StoryText doesn't handle tkMessageBox, deal with it via interception by default
                comment = "Tkinter doesn't provide any means to simulate interaction with tkMessageBox.\n" + \
                          "Therefore StoryText cannot handle it. So we capture interaction with it instead.\n" + \
                          "Cannot have multiple threads interacting with tkinter so we disable the threading also."
                configEntries["section_comment"] = comment
                configEntries["import_config_file"] = "capturemock_config"
                cpMockFileName = os.path.join(directory, "capturemockrc." + ext)
                with open(cpMockFileName, "w") as f:
                    f.write("[python]\n" +
                            "intercepts = tkMessageBox\n\n" + 
                            "[general]\n" +
                            "server_multithreaded = False\n")
            elif useGui == 3:
                comment = "wxPython GUIs don't seem to work very well when the hide flag is set on Windows.\n" + \
                          "So we disable it by default here: multiple desktops may be useful."
                configEntries["section_comment"] = comment
                configEntries["virtual_display_hide_windows"] = "false"
            
            storytextDir = os.path.join(directory, "storytext_files")
            plugins.ensureDirectoryExists(storytextDir) 
            # Create an empty UI map file so it shows up in the Config tab...
            open(os.path.join(storytextDir, "ui_map.conf"), "w")
        elif useGui == 8:
            configEntries["use_case_recorder"] = "none"            

        self.notify("NewApplication", ext, directory, configEntries)
        self.notify("Status", "Created new application with extension '" + ext + "'.")

    def findFullDirectoryPath(self, subdir):
        for rootDir in self.rootDirectories:
            candidate = os.path.normpath(os.path.join(rootDir, subdir))
            if os.path.isdir(candidate):
                return candidate
        return os.path.normpath(os.path.join(self.rootDirectories[0], subdir))
        

class ImportFiles(guiplugins.ActionDialogGUI):
    def __init__(self, allApps, dynamic, inputOptions):
        self.creationDir = None
        self.defaultAppendAppName = False
        self.appendAppName = False
        self.currentStem = ""
        self.fileChooser = None
        self.newFileInfo = (None, False)
        guiplugins.ActionDialogGUI.__init__(self, allApps, dynamic, inputOptions)
        self.addOption("stem", "Type of file/directory to create", allocateNofValues=2)
        self.addOption("v", "Version identifier to use")
        possibleDirs = self.getPossibleDirs(allApps, inputOptions)
        # The point of this is that it's never sensible as the source for anything, so it serves as a "use the parent" option
        # for back-compatibility
        self.addSwitch("act", options=[ "Import file/directory from source", "Create a new file", "Create a new directory" ])
        self.addOption("src", "Source to copy from", selectFile=True, possibleDirs=possibleDirs)
        
    def getPossibleDirs(self, allApps, inputOptions):
        if len(allApps) > 0:
            return sorted(set((app.getDirectory() for app in allApps)))
        else:
            return inputOptions.rootDirectories
                
    def singleTestOnly(self):
        return True
    def _getTitle(self):
        return "Create/_Import"
    def getTooltip(self):
        return "Create a new file or directory, possibly by copying it" 
    def _getStockId(self):
        return "new"
    def getDialogTitle(self):
        return "Create/Import Files and Directories"
    def isActiveOnCurrent(self, *args):
        return self.creationDir is not None and guiplugins.ActionDialogGUI.isActiveOnCurrent(self, *args)
    def getSizeAsWindowFraction(self):
        # size of the dialog
        return 0.7, 0.9
    def getSignalsSent(self):
        return [ "NewFile" ]
    def messageAfterPerform(self):
        pass

    def updateOptions(self):
        self.currentStem = ""
        return False

    def fillVBox(self, vbox, group):
        test = self.currTestSelection[0]
        dirText = self.getDirectoryText(test)
        self.addText(vbox, "<b><u>" + dirText + "</u></b>")
        self.addText(vbox, "<i>(Test is " + repr(test) + ")</i>")
        return guiplugins.ActionDialogGUI.fillVBox(self, vbox, group)

    def stemChanged(self, *args):
        option = self.optionGroup.getOption("stem")
        newStem = option.getValue()    
        if newStem in option.possibleValues and newStem != self.currentStem:
            self.currentStem = newStem
            version = self.optionGroup.getOptionValue("v")
            sourcePath = self.getDefaultSourcePath(newStem, version)
            self.optionGroup.setValue("src", sourcePath)
            if self.defaultAppendAppName:
                self.updateAppendAppName(newStem != "testcustomize.py")

    def actionChanged(self, *args):
        if self.fileChooser:
            self.setFileChooserSensitivity()

    def setFileChooserSensitivity(self):
        action = self.optionGroup.getValue("act")
        sensitive = self.fileChooser.get_property("sensitive")
        newSensitive = action == 0
        if newSensitive != sensitive:
            self.fileChooser.set_property("sensitive", newSensitive)
        
    def getTargetPath(self, *args, **kwargs):
        targetPathName = self.getFileName(*args, **kwargs)
        return os.path.join(self.creationDir, targetPathName)
        
    def getDefaultSourcePath(self, stem, version):
        targetPath = self.getTargetPath(stem, version)
        test = self.currTestSelection[0]
        pathNames = test.getAllPathNames(stem, refVersion=version)
        if len(pathNames) > 0:
            firstSource = pathNames[-1]
            if os.path.basename(firstSource).startswith(stem + "." + test.app.name):
                targetPath = self.getTargetPath(stem, version, appendAppName=True)
            if firstSource != targetPath:
                return firstSource
            elif len(pathNames) > 1:
                return pathNames[-2]
        return test.getDirectory()

    def createComboBoxEntry(self, *args):
        combobox, entry = guiplugins.ActionDialogGUI.createComboBoxEntry(self, *args)
        combobox.connect("changed", self.stemChanged)
        return combobox, entry

    def createRadioButtons(self, *args):
        buttons = guiplugins.ActionDialogGUI.createRadioButtons(self, *args)
        buttons[0].connect("toggled", self.actionChanged)
        return buttons

    def createFileChooser(self, *args):
        self.fileChooser = guiplugins.ActionDialogGUI.createFileChooser(self, *args)
        self.fileChooser.set_name("Source File Chooser")
        self.setFileChooserSensitivity() # Check initial values, maybe set insensitive
        return self.fileChooser
    
    def addText(self, vbox, text):
        header = gtk.Label()
        header.set_markup(text + "\n")
        vbox.pack_start(header, expand=False, fill=False)
    
    def getDirectoryText(self, test):
        relDir = plugins.relpath(self.creationDir, test.getDirectory())
        if relDir:
            return "Create or import files in test subdirectory '" + relDir + "'"
        else:
            return "Create or import files in the test directory"

    def notifyFileCreationInfo(self, creationDir, fileType):
        self.fileChooser = None
        if fileType == "external":
            self.creationDir = None
            self.setSensitivity(False)
        else:
            self.creationDir = creationDir
            newActive = creationDir is not None
            self.setSensitivity(newActive)
            if newActive:
                self.updateStems(fileType)
                self.defaultAppendAppName = (fileType == "definition" or fileType == "standard")
                self.updateAppendAppName(self.defaultAppendAppName)

    def updateAppendAppName(self, setting):
        self.appendAppName = setting
        self.optionGroup.setValue("act", int(setting))

    def findAllStems(self, fileType):
        if fileType == "definition":
            return self.getDefinitionFiles()
        elif fileType == "data":
            return self.currTestSelection[0].getDataFileNames()
        elif fileType == "standard":
            return self.getStandardFiles()
        else:
            return []

    def getDefinitionFiles(self):
        defFiles = []
        defFiles.append("environment")
        defFiles.append("config")
        defFiles.append("options")
        if self.currTestSelection[0].getConfigValue("interpreter"):
            defFiles.append("interpreter_options")
        if self.currTestSelection[0].classId() == "test-case":
            recordMode = self.currTestSelection[0].getConfigValue("use_case_record_mode")
            if recordMode == "disabled":
                namingScheme = self.currTestSelection[0].getConfigValue("filename_convention_scheme")
                defFiles.append(self.currTestSelection[0].app.getStdinName(namingScheme))
            else:
                defFiles.append("usecase")
        # We only want to create files this way that
        # (a) are not created and understood by TextTest itself ("builtin")
        # (b) are not auto-generated ("regenerate")
        # That leaves the rest ("default")
        return defFiles + self.currTestSelection[0].expandedDefFileStems("default")

    def getStandardFiles(self):
        app = self.currTestSelection[0].app
        collateKeys = app.getConfigValue("collate_file").keys()
        # Don't pick up "dummy" indicators on Windows...
        namingScheme = app.getConfigValue("filename_convention_scheme")
        stdFiles = [ app.getStdoutName(namingScheme), app.getStderrName(namingScheme) ] + filter(lambda k: k, collateKeys)
        discarded = [ "stacktrace" ] + app.getConfigValue("discard_file")
        return filter(lambda f: f not in discarded, stdFiles)

    def updateStems(self, fileType):
        stems = self.findAllStems(fileType)
        if len(stems) > 0:
            self.optionGroup.setValue("stem", stems[0])
        else:
            self.optionGroup.setValue("stem", "")
        self.optionGroup.setPossibleValues("stem", stems)

    def getFileName(self, stem, version, appendAppName=False):
        fileName = stem
        if self.appendAppName or appendAppName:
            fileName += "." + self.currTestSelection[0].app.name
        if version:
            fileName += "." + version
        return fileName

    def performOnCurrent(self):
        stem = self.optionGroup.getOptionValue("stem")
        version = self.optionGroup.getOptionValue("v")
        action = self.optionGroup.getSwitchValue("act")
        test = self.currTestSelection[0]
        if action > 0: # Create new
            targetPath = self.getTargetPath(stem, version)
            if os.path.exists(targetPath):
                raise plugins.TextTestError, "Not creating file or directory : path already exists:\n" + targetPath

            if action == 1:
                plugins.ensureDirExistsForFile(targetPath)
                file = open(targetPath, "w")
                file.close()
                self.newFileInfo = targetPath, False
            elif action == 2:
                plugins.ensureDirectoryExists(targetPath)
                test.filesChanged()
        else:
            sourcePath = self.optionGroup.getOptionValue("src")
            appendAppName = os.path.basename(sourcePath).startswith(stem + "." + test.app.name)
            targetPath = self.getTargetPath(stem, version, appendAppName)
            plugins.ensureDirExistsForFile(targetPath)
            fileExisted = os.path.exists(targetPath)
            plugins.copyPath(sourcePath, targetPath)
            self.newFileInfo = targetPath, fileExisted

    def endPerform(self):
        # Shouldn't start new actions until the current ones complete, framework doesn't like it
        guiplugins.ActionDialogGUI.endPerform(self)
        fileName, existed = self.newFileInfo
        if fileName:
            self.notify("NewFile", fileName, existed)
            self.newFileInfo = (None, False)


class RemoveTests(guiplugins.ActionGUI):
    def __init__(self, *args, **kw):
        self.distinctTestCount = 0
        guiplugins.ActionGUI.__init__(self, *args, **kw)
    
    def isActiveOnCurrent(self, *args):
        return any((test.parent for test in self.currTestSelection))

    def getActionName(self):
        return "Remove Tests"

    def _getTitle(self):
        return "Remove Tests..."

    def _getStockId(self):
        return "delete"

    def getTooltip(self):
        return "Remove selected tests"

    def getTestCountDescription(self):
        desc = plugins.pluralise(self.distinctTestCount, "test")
        diff = len(self.currTestSelection) - self.distinctTestCount
        if diff > 0:
            desc += " (with " + plugins.pluralise(diff, "extra instance") + ")"
        return desc

    def updateSelection(self, tests, apps, rowCount, *args):
        self.distinctTestCount = rowCount
        return guiplugins.ActionGUI.updateSelection(self, tests, apps, rowCount, *args)

    def getFileRemoveWarning(self):
        return "This will remove files from the file system and hence may not be reversible."

    def getConfirmationMessage(self):
        extraLines = "\n\nNote: " + self.getFileRemoveWarning() + "\n\nAre you sure you wish to proceed?\n"""
        currTest = self.currTestSelection[0]
        if len(self.currTestSelection) == 1:
            if currTest.classId() == "test-case":
                return "\nYou are about to remove the test '" + currTest.name + \
                       "' and all associated files." + extraLines
            else:
                return "\nYou are about to remove the entire test suite '" + currTest.name + \
                       "' and all " + str(currTest.size()) + " tests that it contains." + extraLines
        else:
            return "\nYou are about to remove " + self.getTestCountDescription() + \
                   " and all associated files." + extraLines

    def getTestsToRemove(self, list):
        toRemove = []
        warnings = ""
        for test in list:
            if not test.parent:
                warnings += "\nThe root suite\n'" + test.name + " (" + test.app.name + ")'\ncannot be removed.\n"
                continue
            if test.classId() == "test-suite":
                subTests, subWarnings = self.getTestsToRemove(test.testcases)
                warnings += subWarnings
                for subTest in subTests:
                    if not subTest in toRemove:
                        toRemove.append(subTest)
            if not test in toRemove:
                toRemove.append(test)

        return toRemove, warnings

    def performOnCurrent(self):
        namesRemoved = []
        toRemove, warnings = self.getTestsToRemove(self.currTestSelection)
        permMessage = "Failed to remove test: didn't have sufficient write permission to the test files"
        for test in toRemove:
            dir = test.getDirectory()
            if os.path.isdir(dir):
                plugins.tryFileChange(self.removePath, permMessage, dir)
            if plugins.tryFileChange(test.remove, permMessage):
                namesRemoved.append(test.name)
        self.notify("Status", "Removed test(s) " + ",".join(namesRemoved))
        if warnings:
            self.showWarningDialog(warnings)

    @staticmethod
    def removePath(dir):
        return plugins.removePath(dir)
    
    def messageAfterPerform(self):
        pass # do it as part of the method as currentTest will have changed by the end!

class RemoveTestsForPopup(RemoveTests):
    def _getTitle(self):
        return "Remove..."

    def getActionName(self):
        return "Remove Tests For Popup"

    
class RemoveFiles(guiplugins.ActionGUI):
    def notifyFileCreationInfo(self, creationDir, fileType):
        canRemove = fileType != "external" and \
                    (creationDir is None or len(self.currFileSelection) > 0) and \
                    self.isActiveOnCurrent()
        self.setSensitivity(canRemove)

    def isActiveOnCurrent(self, *args):
        return len(self.currFileSelection) > 0

    def getActionName(self):
        return "Remove Files"

    def _getTitle(self):
        return "Remove..."

    def _getStockId(self):
        return "delete"

    def getTooltip(self):
        return "Remove selected files"

    def getFileRemoveWarning(self):
        return "This will remove files from the file system and hence may not be reversible."
        
    def getConfirmationMessage(self):
        extraLines = "\n\nNote: " + self.getFileRemoveWarning() + "\n\nAre you sure you wish to proceed?\n"""
        currTest = self.currTestSelection[0]
        return "\nYou are about to remove " + plugins.pluralise(len(self.currFileSelection), self.getType(self.currFileSelection[0][0])) + \
                   " from the " + currTest.classDescription() + " '" + currTest.name + "'." + extraLines

    @staticmethod
    def removePath(dir):
        return plugins.removePath(dir)
    
    def getType(self, filePath):
        if os.path.isdir(filePath):
            return "directory"
        else:
            return "file"

    def performOnCurrent(self):
        test = self.currTestSelection[0]
        removed = 0
        for filePath, _ in self.currFileSelection:
            fileType = self.getType(filePath)
            self.notify("Status", "Removing " + fileType + " " + os.path.basename(filePath))
            self.notify("ActionProgress")
            permMessage = "Insufficient permissions to remove " + fileType + " '" + filePath + "'"
            if plugins.tryFileChange(self.removePath, permMessage, filePath):
                removed += 1

        test.filesChanged()
        self.notify("Status", "Removed " + plugins.pluralise(removed, fileType) + " from the " +
                    test.classDescription() + " " + test.name + "")

    def messageAfterPerform(self):
        pass # do it as part of the method, uses lots of local data


class RepositionTest(guiplugins.ActionGUI):
    def singleTestOnly(self):
        return True
    def _isActiveOnCurrent(self):
        return guiplugins.ActionGUI.isActiveOnCurrent(self) and \
               self.currTestSelection[0].parent and \
               not self.currTestSelection[0].parent.autoSortOrder
    def getSignalsSent(self):
        return [ "RefreshTestSelection" ]

    def performOnCurrent(self):
        newIndex = self.findNewIndex()
        test = self.currTestSelection[0]
        permMessage = "Failed to reposition test: no permissions to edit the testsuite file"
                
        if plugins.tryFileChange(test.parent.repositionTest, permMessage, test, newIndex):
            self.notify("RefreshTestSelection")
        else:
            raise plugins.TextTestError, "\nThe test\n'" + test.name + "'\nis not present in the default version\nand hence cannot be reordered.\n"

class RepositionTestDown(RepositionTest):
    def _getStockId(self):
        return "go-down"
    def _getTitle(self):
        return "Move down"
    def messageAfterPerform(self):
        return "Moved " + self.describeTests() + " one step down in suite."
    def getTooltip(self):
        return "Move selected test down in suite"
    def findNewIndex(self):
        return min(self.currTestSelection[0].positionInParent() + 1, self.currTestSelection[0].parent.maxIndex())
    def isActiveOnCurrent(self, *args):
        if not self._isActiveOnCurrent():
            return False
        return self.currTestSelection[0].parent.testcases[self.currTestSelection[0].parent.maxIndex()] != self.currTestSelection[0]

class RepositionTestUp(RepositionTest):
    def _getStockId(self):
        return "go-up"
    def _getTitle(self):
        return "Move up"
    def messageAfterPerform(self):
        return "Moved " + self.describeTests() + " one step up in suite."
    def getTooltip(self):
        return "Move selected test up in suite"
    def findNewIndex(self):
        return max(self.currTestSelection[0].positionInParent() - 1, 0)
    def isActiveOnCurrent(self, *args):
        if not self._isActiveOnCurrent():
            return False
        return self.currTestSelection[0].parent.testcases[0] != self.currTestSelection[0]

class RepositionTestFirst(RepositionTest):
    def _getStockId(self):
        return "goto-top"
    def _getTitle(self):
        return "Move to first"
    def messageAfterPerform(self):
        return "Moved " + self.describeTests() + " to first in suite."
    def getTooltip(self):
        return "Move selected test to first in suite"
    def findNewIndex(self):
        return 0
    def isActiveOnCurrent(self, *args):
        if not self._isActiveOnCurrent():
            return False
        return self.currTestSelection[0].parent.testcases[0] != self.currTestSelection[0]

class RepositionTestLast(RepositionTest):
    def _getStockId(self):
        return "goto-bottom"
    def _getTitle(self):
        return "Move to last"
    def messageAfterPerform(self):
        return "Moved " + repr(self.currTestSelection[0]) + " to last in suite."
    def getTooltip(self):
        return "Move selected test to last in suite"
    def findNewIndex(self):
        return self.currTestSelection[0].parent.maxIndex()
    def isActiveOnCurrent(self, *args):
        if not self._isActiveOnCurrent():
            return False
        currLastTest = self.currTestSelection[0].parent.testcases[len(self.currTestSelection[0].parent.testcases) - 1]
        return currLastTest != self.currTestSelection[0]

class RenameAction(guiplugins.ActionDialogGUI):
    def singleTestOnly(self):
        return True

    def _getStockId(self):
        return "italic"

    def _getTitle(self):
        return "_Rename..."

    def messageAfterPerform(self):
        pass # Use method below instead.

    def basicNameCheck(self, newName):
        if len(newName) == 0:
            raise plugins.TextTestError, "Please enter a new name."
        if " " in newName:
            raise plugins.TextTestError, "The new name must not contain spaces, please choose another name."

    def performOnCurrent(self):
        try:
            newName = self.optionGroup.getOptionValue("name")
            self.basicNameCheck(newName)
            self.performRename(newName)
        except (IOError, OSError), e:
            self.showErrorDialog("Failed to " + self.getActionName().lower() + ":\n" + str(e))

    @staticmethod
    def movePath(oldPath, newPath):
        # overridden by version control modules
        os.rename(oldPath, newPath)


class RenameTest(RenameAction):
    def __init__(self, *args):
        RenameAction.__init__(self, *args)
        self.addOption("name", "\nNew name")
        self.addOption("desc", "\nNew description", multilineEntry=True)
        self.oldName = ""
        self.oldDescription = ""

    def getSizeAsWindowFraction(self):
        # size of the dialog
        return 0.5, 0.36
    
    def isActiveOnCurrent(self, *args):
        # Don't allow renaming of the root suite
        return guiplugins.ActionGUI.isActiveOnCurrent(self, *args) and bool(self.currTestSelection[0].parent)

    def updateOptions(self):
        self.oldName = self.currTestSelection[0].name
        self.oldDescription = self.currTestSelection[0].description
        self.optionGroup.setOptionValue("name", self.oldName)
        self.optionGroup.setOptionValue("desc", self.oldDescription)
        return True

    def fillVBox(self, vbox, group):
        header = gtk.Label()
        header.set_markup("<b>" + plugins.convertForMarkup(self.oldName) + "</b>")
        vbox.pack_start(header, expand=False, fill=False)
        return guiplugins.ActionDialogGUI.fillVBox(self, vbox, group)
    
    def getTooltip(self):
        return "Rename selected test"

    def getActionName(self):
        return "Rename Test"

    def getNameChangeMessage(self, newName):    
        return "Renamed test " + self.oldName + " to " + newName

    def getChangeMessage(self, newName, newDesc):
        if self.oldName != newName:
            message = self.getNameChangeMessage(newName)
            if self.oldDescription != newDesc:
                message += " and changed description."
            else:
                message += "."
        elif newDesc != self.oldDescription:
            message = "Changed description of test " + self.oldName + "."
        else:
            message = "Nothing changed."
        return message
    
    def checkNewName(self, newName):
        if newName != self.oldName:
            for test in self.currTestSelection[0].parent.testCaseList():
                if test.name == newName:
                    raise plugins.TextTestError, "The name '" + newName + "' is already taken, please choose another name."
            newDir = os.path.join(self.currTestSelection[0].parent.getDirectory(), newName)
            if os.path.isdir(newDir):
                self.handleExistingDirectory(newDir)

    def handleExistingDirectory(self, newDir): # In CVS we might need to override this...
        raise plugins.TextTestError, "The directory " + newDir + " already exists, please choose another name."

    def performRename(self, newName):
        self.checkNewName(newName)
        newDesc = self.optionGroup.getOptionValue("desc")
        if newName != self.oldName or newDesc != self.oldDescription:
            for test in self.currTestSelection:
                # Do this first, so that if we fail we won't update the test suite files either
                self.moveFiles(test, newName)
                test.rename(newName, newDesc)
        changeMessage = self.getChangeMessage(newName, newDesc)
        self.oldName = newName
        self.oldDescription = newDesc
        self.notify("Status", changeMessage)
        
    def moveFiles(self, test, newName):
        # Create new directory, copy files if the new name is new (we might have
        # changed only the comment ...)
        if test.name != newName:
            oldDir = test.getDirectory()
            newDir = test.parent.getNewDirectoryName(newName)
            if os.path.isdir(oldDir):
                self.movePath(oldDir, newDir)


class RenameFile(RenameAction):
    def __init__(self, *args):
        RenameAction.__init__(self, *args)
        self.addOption("name", "\nNew name for file")
        self.oldName = ""

    def notifyFileCreationInfo(self, creationDir, fileType):
        canRename = fileType != "external" and \
                    (creationDir is None or len(self.currFileSelection) > 0) and \
                    self.isActiveOnCurrent()
        self.setSensitivity(canRename)

    def isActiveOnCurrent(self, *args):
        return len(self.currFileSelection) == 1

    def singleTestOnly(self):
        return True

    def updateOptions(self):
        self.oldName = os.path.basename(self.currFileSelection[0][0])
        self.optionGroup.setOptionValue("name", self.oldName)
        return True

    def _getStockId(self):
        return "italic"

    def getActionName(self):
        return "Rename File"

    def _getTitle(self):
        return "_Rename..."
    
    def getTooltip(self):
        return "Rename selected file"

    def messageAfterPerform(self):
        pass # Use method below instead.

    def getNameChangeMessage(self, newName):    
        return "Renamed file " + self.oldName + " to " + newName + "."

    def checkNewName(self, newName, newPath):
        if newName == self.oldName:
            raise plugins.TextTestError, "Please enter a new name."
        if os.path.exists(newPath):
            raise plugins.TextTestError, "There is already a file or directory at '" + newName + "', please choose another name."

    def getConfirmationMessage(self):
        oldStem = self.oldName.split(".")[0]
        newName = self.optionGroup.getOptionValue("name")
        newStem = newName.split(".")[0]
        if self.currTestSelection[0].isDefinitionFileStem(oldStem) and \
               not self.currTestSelection[0].isDefinitionFileStem(newStem):
            return "You are trying to rename a definition file in such a way that it will no longer fulfil its previous purpose.\nTextTest uses conventional names for files with certain purposes and '" + oldStem + "' is one such conventional name.\nAre you sure you want to continue?"
        else:
            return ""

    def performRename(self, newName):
        oldPath = self.currFileSelection[0][0]
        newPath = os.path.join(os.path.dirname(oldPath), newName)
        self.checkNewName(newName, newPath)
        self.movePath(oldPath, newPath)
        self.currTestSelection[0].filesChanged()
        changeMessage = self.getNameChangeMessage(newName)
        self.oldName = newName
        self.notify("Status", changeMessage)
                

class SortTestSuiteFileAscending(guiplugins.ActionGUI):
    def singleTestOnly(self):
        return True
    def correctTestClass(self):
        return "test-suite"
    def isActiveOnCurrent(self, *args):
        return guiplugins.ActionGUI.isActiveOnCurrent(self, *args) and not self.currTestSelection[0].autoSortOrder
    def _getStockId(self):
        return "sort-ascending"
    def _getTitle(self):
        return "_Sort Test Suite File"
    def messageAfterPerform(self):
        return "Sorted testsuite file for " + self.describeTests() + " in alphabetical order."
    def getTooltip(self):
        return "sort testsuite file for the selected test suite in alphabetical order"
    def performOnCurrent(self):
        self.performRecursively(self.currTestSelection[0], True)
    def performRecursively(self, suite, ascending):
        # First ask all sub-suites to sort themselves
        if guiutils.guiConfig.getValue("sort_test_suites_recursively"):
            for test in suite.testcases:
                if test.classId() == "test-suite":
                    self.performRecursively(test, ascending)
                    
        self.notify("Status", "Sorting " + repr(suite))
        self.notify("ActionProgress")
        if self.hasNonDefaultTests():
            self.showWarningDialog("\nThe test suite\n'" + suite.name + "'\ncontains tests which are not present in the default version.\nTests which are only present in some versions will not be\nmixed with tests in the default version, which might lead to\nthe suite not looking entirely sorted.")

        suite.sortTests(ascending)
        
    def hasNonDefaultTests(self):
        if len(self.currTestSelection) == 1:
            return False

        for extraSuite in self.currTestSelection[1:]:
            for test in extraSuite.testcases:
                if not self.currTestSelection[0].findSubtest(test.name):
                    return True
        return False


class SortTestSuiteFileDescending(SortTestSuiteFileAscending):
    def _getStockId(self):
        return "sort-descending"
    def _getTitle(self):
        return "_Reversed Sort Test Suite File"
    def messageAfterPerform(self):
        return "Sorted testsuite file for " + self.describeTests() + " in reversed alphabetical order."
    def getTooltip(self):
        return "sort testsuite file for the selected test suite in reversed alphabetical order"
    def performOnCurrent(self):
        self.performRecursively(self.currTestSelection[0], False)


class ReportBugs(guiplugins.ActionDialogGUI):
    def __init__(self, allApps, *args):
        guiplugins.ActionDialogGUI.__init__(self, allApps, *args)
        self.textGroup = plugins.OptionGroup("Search for")
        self.searchGroup = plugins.OptionGroup("Search in")
        self.applyGroup = plugins.OptionGroup("Additional options to only apply to certain runs")
        self.bugSystemGroup = plugins.OptionGroup("Link failure to a reported bug")
        self.textDescGroup = plugins.OptionGroup("Link failure to a textual description")
        self.textGroup.addOption("search_string", "Text or regexp to match")
        self.textGroup.addSwitch("trigger_on_absence", "Trigger if given text is NOT present")
        self.searchGroup.addSwitch("data_source", options = [ "Specific file", "Brief text/details", "Full difference report" ], description = [ "Search in a newly generated file (not its diff)", "Search in the brief text describing the test result as it appears in the Details column in the dynamic GUI test view", "Search in the whole difference report as it appears in the lower right window in the dynamic GUI" ])
        self.searchGroup.addOption("search_file", "File to search in")
        self.searchGroup.addSwitch("ignore_other_errors", "Trigger even if other files differ", description="By default, this bug is only enabled if only the provided file is different. Check this box to enable it irrespective of what other difference exist. Note this increases the chances of it being reported erroneously and should be used carefully.")
        self.searchGroup.addSwitch("trigger_on_success", "Trigger even if file to search would otherwise compare as equal", description="By default, this bug is only enabled if a difference is detected in the provided file to search. Check this box to search for it even if the file compares as equal.")
        
        self.applyGroup.addOption("version", "\nVersion to report for")
        self.applyGroup.addOption("execution_hosts", "Trigger only when run on machine(s)")
        self.bugSystemGroup.addOption("bug_system", "\nExtract info from bug system", "<none>", self.findBugSystems(allApps))
        self.bugSystemGroup.addOption("bug_id", "Bug ID")
        self.textDescGroup.addOption("full_description", "\nFull description")
        self.textDescGroup.addOption("brief_description", "Few-word summary")
        self.textDescGroup.addSwitch("internal_error", "Report as 'internal error' rather than 'known bug'")
        self.optionGroup.addOption("rerun_count", "Number of times to try to rerun the test if the issue is triggered", 0)

    def fillVBox(self, vbox, optionGroup):
        if optionGroup is self.optionGroup:
            for group in [ self.textGroup, self.searchGroup, self.applyGroup ]:
                if group is self.applyGroup:
                    widget = self.createExpander(group)
                else:
                    widget = self.createFrame(group, group.name)
                vbox.pack_start(widget, fill=False, expand=False, padding=8)
            vbox.pack_start(gtk.HSeparator(), padding=8)
            header = gtk.Label()
            header.set_markup("<u>Fill in exactly <i>one</i> of the sections below</u>\n")
            vbox.pack_start(header, expand=False, fill=False, padding=8)
            for group in [ self.bugSystemGroup, self.textDescGroup ]:
                frame = self.createFrame(group, group.name)
                vbox.pack_start(frame, fill=False, expand=False, padding=8)
        return guiplugins.ActionDialogGUI.fillVBox(self, vbox, optionGroup)

    def createExpander(self, group):
        expander = gtk.Expander(group.name)
        expander.add(self.createGroupBox(group))
        return expander

    def createRadioButtons(self, *args):
        buttons = guiplugins.ActionDialogGUI.createRadioButtons(self, *args)
        buttons[0].connect("toggled", self.dataSourceChanged)
        return buttons

    def dataSourceChanged(self, *args):
        sensitive = not self.searchGroup.getOptionValue("data_source")
        self.setGroupSensitivity(self.searchGroup, sensitive)
        
    def findBugSystems(self, allApps):
        bugSystems = []
        for app in allApps:
            for appSystem in app.getConfigValue("bug_system_location").keys():
                if appSystem not in bugSystems:
                    bugSystems.append(appSystem)
        return bugSystems
            
    def _getStockId(self):
        return "info"

    def singleTestOnly(self):
        return True

    def _getTitle(self):
        return "Enter Failure Information"

    def getDialogTitle(self):
        return "Enter information for automatic interpretation of test failures"

    def updateOptions(self):
        if not self.searchGroup.getOptionValue("search_file"):
            self.searchGroup.setOptionValue("search_file", self.currTestSelection[0].getConfigValue("log_file"))

        self.searchGroup.setPossibleValues("search_file", self.getPossibleFileStems())
        return False

    def getPossibleFileStems(self):
        stems = []
        excludeStems = self.currTestSelection[0].expandedDefFileStems()
        for test in self.currTestSelection[0].testCaseList():
            for stem in test.dircache.findAllStems():
                if stem not in stems and stem not in excludeStems:
                    stems.append(stem)
        return stems

    def checkSanity(self):
        if len(self.textGroup.getOptionValue("search_string")) == 0:
            raise plugins.TextTestError, "Must fill in the field 'text or regexp to match'"
        if self.bugSystemGroup.getOptionValue("bug_system") == "<none>":
            if len(self.textDescGroup.getOptionValue("full_description")) == 0 or \
                   len(self.textDescGroup.getOptionValue("brief_description")) == 0:
                raise plugins.TextTestError, "Must either provide a bug system or fill in both description and summary fields"
        else:
            if len(self.bugSystemGroup.getOptionValue("bug_id")) == 0:
                raise plugins.TextTestError, "Must provide a bug ID if bug system is given"

    def versionSuffix(self):
        version = self.applyGroup.getOptionValue("version")
        if len(version) == 0:
            return ""
        else:
            return "." + version

    def getFileName(self):
        name = "knownbugs." + self.currTestSelection[0].app.name + self.versionSuffix()
        return os.path.join(self.currTestSelection[0].getDirectory(), name)

    def getSizeAsWindowFraction(self):
        # size of the dialog
        return 0.6, 0.6
    
    def performOnCurrent(self):
        self.checkSanity()
        dataSourceText = { 1 : "brief_text", 2 : "free_text" }
        namesToIgnore = [ "version" ]
        fileName = self.getFileName()
        writeFile = open(fileName, "a")
        writeFile.write("\n[Reported by " + os.getenv("USER", "Windows") + " at " + plugins.localtime() + "]\n")
        for group in [ self.textGroup, self.searchGroup, self.applyGroup,
                       self.bugSystemGroup, self.textDescGroup, self.optionGroup ]:
            for name, option in group.options.items():
                value = option.getValue()
                if name in namesToIgnore or not value or value in [ "0", "<none>" ]:
                    continue
                if name == "data_source":
                    writeFile.write("search_file:" + dataSourceText[value] + "\n")
                    namesToIgnore += [ "search_file", "trigger_on_success", "ignore_other_errors" ]
                else:
                    writeFile.write(name + ":" + str(value) + "\n")
        writeFile.close()
        self.currTestSelection[0].filesChanged()


def getInteractiveActionClasses():
    return [ CopyTests, CutTests, PasteTests,
             ImportTestCase, ImportTestSuite, ImportApplication, ImportFiles,
             RenameTest, RenameFile, RemoveTests, RemoveTestsForPopup, RemoveFiles, ReportBugs,
             SortTestSuiteFileAscending, SortTestSuiteFileDescending,
             RepositionTestFirst, RepositionTestUp, RepositionTestDown, RepositionTestLast ]
