#!/usr/bin/env python
import os, sys, types, string, plugins, exceptions, shutil, operator, logging, glob, fnmatch
from ordereddict import OrderedDict
from cPickle import Pickler, loads, UnpicklingError
from threading import Lock
from tempfile import mkstemp
from copy import deepcopy

helpIntro = """
Note: the purpose of this help is primarily to document derived configurations and how they differ from the
defaults. To find information on the configurations provided with texttest, consult the documentation at
http://www.texttest.org
"""

class DirectoryCache:
    def __init__(self, dir):
        self.dir = dir
        self.contents = []
        self.refresh()

    def refresh(self):
        try:
            self.contents = os.listdir(self.dir)
            self.contents.sort()
        except OSError: # usually caused by people removing stuff externally
            self.contents = []

    def hasStem(self, stem):
        for fileName in self.contents:
            if fileName.startswith(stem):
                return True
        return False

    def exists(self, fileName):
        return fileName in self.contents

    def pathName(self, fileName):
        return os.path.join(self.dir, fileName)

    def splitStem(self, fileName):
        parts = fileName.split(".")
        return parts[0], frozenset(parts[1:])

    def findVersionSet(self, fileName, stem):
        if fileName.startswith(stem):
            fileStem, versions = self.splitStem(fileName[len(stem):])
            if len(fileStem) == 0:
                return versions

    def findAllFiles(self, stem, extensionPred=None):
        versionSets = self.findVersionSets(stem, extensionPred)
        return reduce(operator.add, versionSets.values(), [])

    def findVersionSets(self, stem, predicate):
        if "/" in stem:
            root, local = os.path.split(stem)
            newCache = DirectoryCache(os.path.join(self.dir, root))
            return newCache.findVersionSets(local, predicate)

        versionSets = OrderedDict()
        for fileName in self.contents:
            versionSet = self.findVersionSet(fileName, stem)
            if versionSet is not None and (predicate is None or predicate(versionSet)):
                versionSets.setdefault(versionSet, []).append(self.pathName(fileName))
        return versionSets

    def findStemsMatching(self, pattern):
        return self.findAllStems(lambda stem, vset: fnmatch.fnmatch(stem, pattern))

    def findAllStems(self, predicate=None):
        stems = []
        for file in self.contents:
            stem, versionSet = self.splitStem(file)
            if len(stem) > 0 and stem not in stems and (predicate is None or predicate(stem, versionSet)):
                stems.append(stem)
        return stems


class DynamicMapping:
    def __init__(self, method, *args):
        self.method = method
        self.extraArgs = args
    def __getitem__(self, key):
        value = self.method(key, *self.extraArgs)
        if value is not None:
            return value
        else:
            raise KeyError, "No such value " + key


class TestEnvironment(OrderedDict):
    def __init__(self, populateFunction):
        OrderedDict.__init__(self)
        self.diag = logging.getLogger("read environment")
        self.populateFunction = populateFunction
        self.populated = False

    def checkPopulated(self):
        if not self.populated:
            self.populated = True
            self.populateFunction()

    def definesValue(self, var):
        self.checkPopulated()
        return self.has_key(var)

    def copy(self):
        # Shallow copies should contain all the information locally, otherwise deepcopying effectively happens.
        return self.getValues()
    
    def getValues(self, onlyVars=[], ignoreVars=[]):
        self.checkPopulated()
        values = {}
        varsToUnset = []
        for key, value in self.items():
            # Anything set to none is to not to be set in the target environment
            if value is not None and value != "{CLEAR}":
                if len(onlyVars) == 0 or key in onlyVars:
                    values[key] = value
            else:
                varsToUnset.append(key)
        varsToUnset += ignoreVars
        self.diag.info("Removing variables " + repr(varsToUnset))
        # copy in the external environment last
        return plugins.copyEnvironment(values, varsToUnset)

    def __getitem__(self, var):
        value = self.getSingleValue(var)
        if value is not None:
            return value
        else:
            raise KeyError, "No such value " + var

    def getSingleValue(self, var, defaultValue=None):
        self.checkPopulated()
        return self._getSingleValue(var, defaultValue)

    def _getSingleValue(self, var, defaultValue=None):
        value = self.get(var, os.getenv(var, defaultValue))
        self.diag.info("Single: got " + var + " = " + repr(value))
        return value
    
    def getSelfReference(self, var, originalVar):
        if var == originalVar:
            return self._getSingleValue(var)

    def getSingleValueNoSelfRef(self, var, originalVar):
        if var != originalVar:
            return self._getSingleValue(var)

    def storeVariables(self, vars):
        for var, valueOrMethod in vars:
            newValue = self.expandSelfReferences(var, valueOrMethod)
            if newValue is not None:
                self.diag.info("Storing " + var + " = " + repr(newValue))
                self[var] = newValue
                
        while self.expandVariables():
            pass

    def expandSelfReferences(self, var, valueOrMethod):
        if type(valueOrMethod) == types.StringType:
            mapping = DynamicMapping(self.getSelfReference, var)
            self.diag.info("Expanding self references for " + repr(var) + " in " + repr(valueOrMethod))
            return string.Template(valueOrMethod).safe_substitute(mapping)
        else:
            return valueOrMethod(var, self._getSingleValue(var, ""))

    def expandVariables(self):
        expanded = False
        for var, value in self.iteritems():
            mapping = DynamicMapping(self.getSingleValueNoSelfRef, var)
            newValue = string.Template(value).safe_substitute(mapping)
            if newValue != value:
                expanded = True
                self.diag.info("Expanded " + var + " = " + newValue)
                self[var] = newValue
        return expanded

        
# Base class for TestCase and TestSuite
class Test(plugins.Observable):
    def __init__(self, name, description, dircache, app, parent=None):
        # Should notify which test it is
        plugins.Observable.__init__(self, passSelf=True)
        self.name = name
        self.description = description
        # There is nothing to stop several tests having the same name. Maintain another name known to be unique
        self.uniqueName = name
        self.app = app
        self.parent = parent
        self.dircache = dircache
        self.configDir = None
        if parent is not None:
            self.reloadConfiguration()
        populateFunction = plugins.Callable(app.setEnvironment, self)
        self.environment = TestEnvironment(populateFunction)
        # Java equivalent of the environment mechanism...
        self.properties = plugins.MultiEntryDictionary()
        self.diag = logging.getLogger("test objects")
        # Test suites never change state, but it's convenient that they have one
        self.state = plugins.TestState("not_started")

    def reloadConfiguration(self):
        if self.dircache.hasStem("config." + self.app.name):
            parentConfigDir = self.getParentConfigDir()
            newConfigDir = deepcopy(parentConfigDir)
            self.app.readValues(newConfigDir, "config", [ self.dircache ], insert=False, errorOnUnknown=True)
            self.configDir = newConfigDir

    def getParentConfigDir(self):
        # Take the immediate parent first, upwards to the root suite
        # Don't include self!
        for suite in reversed(self.getAllTestsToRoot()[:-1]):
            if suite.configDir:
                return suite.configDir
        return self.app.configDir
        
    def __repr__(self):
        return repr(self.app) + " " + self.classId() + " " + self.name

    def paddedRepr(self):
        return repr(self.app) + " " + self.classId() + " " + self.paddedName()

    def paddedName(self):
        if not self.parent:
            return self.name
        maxLength = max(len(test.name) for test in self.parent.testcases)
        return self.name.ljust(maxLength)
    
    def changeDirectory(self, newDir, origRelPath):
        self.dircache = DirectoryCache(newDir)
        self.notify("NameChange", origRelPath)
        
    def setName(self, newName):
        if self.name != newName:
            origRelPath = self.getRelPath()
            self.name = newName
            self.changeDirectory(self.parent.getNewDirectoryName(newName), origRelPath)
            self.updateAllRelPaths(origRelPath)
            if self.parent.autoSortOrder:
                self.parent.updateOrder()

    def setDescription(self, newDesc):
        if self.description != newDesc:
            self.description = newDesc
            self.notify("DescriptionChange")

    def classDescription(self):
        return self.classId().replace("-", " ")

    def diagnose(self, message):
        self.diag.info("In test " + self.uniqueName + " : " + message)
        
    def setUniqueName(self, newName):
        if newName != self.uniqueName:
            self.notify("UniqueNameChange", newName)
            self.uniqueName = newName
            
    def setEnvironment(self, var, value):
        self.environment[var] = value

    def addProperty(self, var, value, propFile):
        if not self.properties.has_key(propFile):
            self.properties.addEntry(propFile, {})
        self.properties.addEntry(var, value, sectionName = propFile)

    def getEnvironment(self, var, defaultValue=None):
        return self.environment.getSingleValue(var, defaultValue)

    def hasEnvironment(self, var):
        return self.environment.definesValue(var)

    def needsRecalculation(self): #pragma : no cover - completeness only
        return False

    def classId(self): #pragma : no cover - completeness only
        return "Test Base"

    def isAcceptedBy(self, *args): #pragma : no cover - completeness only
        return False

    def isEmpty(self):
        return False
    
    def readContents(self, *args, **kw):
        return True

    def isDefinitionFileStem(self, stem):
        return self.fileMatches(stem, self.defFileStems())
                
    def defFileStems(self, *args, **kw):
        return self.app.defFileStems(*args, **kw)

    def expandedDefFileStems(self, category="all"):
        stems = []
        for pattern in self.defFileStems(category):
            if glob.has_magic(pattern):
                for test in self.testCaseList():
                    for stem in test.dircache.findStemsMatching(pattern):
                        if stem not in stems:
                            stems.append(stem)
            elif pattern not in stems:
                stems.append(pattern)
        return stems

    def listStandardFiles(self, allVersions, defFileCategory="all"):
        self.diagnose("Looking for standard files, definition files in category " + repr(defFileCategory))
        defFileStems = self.expandedDefFileStems(defFileCategory)
        defFiles = self.getFilesFromStems(defFileStems, allVersions)
        resultFiles = self.listResultFiles(allVersions)
        self.diagnose("Found " + repr(resultFiles) + " and " + repr(defFiles))
        return resultFiles, defFiles

    def listResultFiles(self, allVersions):
        exclude = self.expandedDefFileStems() + self.getDataFileNames() + [ "file_edits" ]
        self.diagnose("Excluding " + repr(exclude))
        predicate = lambda stem, vset: stem not in exclude and len(vset) > 0
        stems = self.dircache.findAllStems(predicate)
        return self.getFilesFromStems(stems, allVersions)

    def getFilesFromStems(self, stems, allVersions):
        files = []
        for stem in stems:
            files += self.listStdFilesWithStem(stem, allVersions)
        return files
    
    def listStdFilesWithStem(self, stem, allVersions):
        self.diagnose("Getting files for stem " + stem)
        files = []
        if allVersions:
            files += self.findAllStdFiles(stem)
        else:
            currFile = self.getFileName(stem)
            if currFile:
                files.append(currFile)
        return files

    def listDataFiles(self):
        existingDataFiles = []
        for dataFile in self.getDataFileNames():
            self.diagnose("Searching for data files called " + dataFile)
            for fileName in self.dircache.findAllFiles(dataFile):
                for fullPath in self.listFiles(fileName, dataFile, followLinks=True):
                    if not fullPath in existingDataFiles:
                        existingDataFiles.append(fullPath)

        self.diagnose("Found data files as " + repr(existingDataFiles))
        return existingDataFiles

    def listFiles(self, fileName, dataFile, followLinks):
        filesToIgnore = self.getCompositeConfigValue("test_data_ignore", dataFile)
        return self.listFilesFrom([ fileName ], filesToIgnore, followLinks)

    def fullPathList(self, dir):
        return map(lambda file: os.path.join(dir, file), os.listdir(dir))

    def listExternallyEditedFiles(self):
        rootDir = self.getFileName("file_edits")
        if rootDir:
            fileList = self.fullPathList(rootDir)
            filesToIgnore = self.getCompositeConfigValue("test_data_ignore", "file_edits")
            return rootDir, self.listFilesFrom(fileList, filesToIgnore, followLinks=True)
        else:
            return None, []

    def listFilesFrom(self, files, filesToIgnore, followLinks):
        files.sort()
        dataFiles = []
        dirs = []
        self.diag.info("Listing files from " + repr(files) + ", ignoring " + repr(filesToIgnore))
        for file in files:
            if self.fileMatches(os.path.basename(file), filesToIgnore):
                continue
            if os.path.isdir(file) and (followLinks or not os.path.islink(file)):
                dirs.append(file)
            else:
                dataFiles.append(file)
        for subdir in dirs:
            dataFiles.append(subdir)
            dataFiles += self.listFilesFrom(self.fullPathList(subdir), filesToIgnore, followLinks)
        return dataFiles

    def fileMatches(self, file, filesToIgnore):
        for ignFile in filesToIgnore:
            if fnmatch.fnmatch(file, ignFile):
                return True
        return False
    
    def findAllStdFiles(self, stem):
        if stem in [ "environment", "testcustomize.py" ]:
            otherApps = self.app.findOtherAppNames()
            self.diagnose("Finding environment files, excluding " + repr(otherApps))
            otherAppExcludor = lambda vset: len(vset.intersection(otherApps)) == 0
            return self.dircache.findAllFiles(stem, otherAppExcludor)
        else:
            return self.app.getAllFileNames([ self.dircache ], stem, allVersions=True)

    def makeSubDirectory(self, name):
        subdir = self.dircache.pathName(name)
        if os.path.isdir(subdir):
            return subdir
        try:
            os.mkdir(subdir)
            return subdir
        except OSError:
            raise plugins.TextTestError, "Cannot create test sub-directory : " + subdir

    def getFileNamesMatching(self, pattern):
        fileNames = []
        for stem in self.dircache.findStemsMatching(pattern):
            fileName = self.getFileName(stem)
            if fileName:
                fileNames.append(fileName)
        return fileNames

    def getAppForVersion(self, refVersion=None):
        if refVersion:
            return self.app.getRefVersionApplication(refVersion)
        else:
            return self.app

    def getFileName(self, stem, refVersion = None):
        self.diagnose("Getting file from " + stem)
        return self.getAppForVersion(refVersion).getFileNameFromCaches([ self.dircache ], stem)

    def getPathName(self, stem, configName=None, refVersion=None):
        app = self.getAppForVersion(refVersion)
        return self.pathNameMethod(stem, configName, app.getFileNameFromCaches)

    def getAllPathNames(self, stem, configName=None, refVersion=None):
        app = self.getAppForVersion(refVersion)
        return self.pathNameMethod(stem, configName, app.getAllFileNames)

    def pathNameMethod(self, stem, configName, method):
        if configName is None:
            configName = stem
        dirCaches = self.getDirCachesToRoot(configName)
        self.diagnose("Directories to be searched: " + repr([ d.dir for d in dirCaches ]))
        return method(dirCaches, stem)

    def getAllTestsToRoot(self):
        tests = [ self ]
        if self.parent:
            tests = self.parent.getAllTestsToRoot() + tests
        return tests

    def updateAllRelPaths(self, origRelPath):
        stdFiles, defFiles = self.listStandardFiles(allVersions=True)
        newRelPath = self.getRelPath()
        for file in stdFiles + defFiles:
            self.updateRelPathReferences(file, origRelPath, newRelPath)

    def getDirCachesToRoot(self, configName):
        fromTests = [ test.dircache for test in self.getAllTestsToRoot() ]
        dirCaches = self.app.getExtraDirCaches(configName, envMapping=self.environment) + fromTests
        if self.app.tmpSettingsDirCache:
            dirCaches.append(self.app.tmpSettingsDirCache)
        return dirCaches

    def getAllFileNames(self, stem, refVersion = None):
        self.diagnose("Getting file from " + stem)
        appToUse = self.app
        if refVersion:
            appToUse = self.app.getRefVersionApplication(refVersion)
        return appToUse.getAllFileNames([ self.dircache ], stem)

    def getConfigValue(self, key, expandVars=True, envMapping=None):
        if envMapping is None:
            envMapping = self.environment
        if self.configDir:
            return self.configDir.getSingle(key, expandVars, envMapping)
        else:
            confObj = self.parent or self.app
            return confObj.getConfigValue(key, expandVars, envMapping)

    def getCompositeConfigValue(self, key, subKey, expandVars=True, envMapping=None):
        if envMapping is None:
            envMapping = self.environment
        if self.configDir:
            return self.configDir.getComposite(key, subKey, expandVars, envMapping)
        else:
            confObj = self.parent or self.app
            return confObj.getCompositeConfigValue(key, subKey, expandVars, envMapping)

    def configValueMatches(self, key, filePattern):
        for currPattern in self.getConfigValue(key):
            if fnmatch.fnmatch(filePattern, currPattern):
                return True
        return False

    def getDataFileNames(self):
        return self.app.getDataFileNames(test=self)
            
    def getRelPath(self):
        if self.parent:
            parentPath = self.parent.getRelPath()
            if parentPath:
                return os.path.join(parentPath, self.name)
            else:
                return self.name
        else:
            return ""

    def getDirectory(self, *args, **kw):
        return self.dircache.dir

    def positionInParent(self):
        if self.parent:
            return self.parent.testcases.index(self)
        else:
            return 0

    def remove(self):
        if self.parent: # might have already removed the enclosing suite
            self.parent.removeFromTestFile(self.name)
            self.removeFromMemory()
            return True
        else:
            return False

    def removeFromMemory(self):
        self.parent.testcases.remove(self)
        self.notify("Remove")

    def getNewDirectoryName(self, newName):
        return self.dircache.pathName(newName)
    
    def rename(self, newName, newDescription):
        # Correct all testsuite files ...
        for testSuiteFileName in self.parent.findTestSuiteFiles():
            self.parent.testSuiteFileHandler.rename(testSuiteFileName, self.name, newName, newDescription)

        # Change the structures and notify the outside world...
        self.setName(newName)
        self.setDescription(newDescription)

    def updateRelPathReferences(self, targetFile, oldRelPath, newRelPath):
        oldRelPath = "/" + oldRelPath
        newRelPath = "/" + newRelPath
        # Binary mode, otherwise Windows line endings get transformed to UNIX ones (even on Windows!)
        # which will cause the test to fail...
        contents = open(targetFile, "rb").read()
        if oldRelPath in contents:
            tmpFile, tmpFileName = mkstemp()
            os.write(tmpFile, contents.replace(oldRelPath, newRelPath))
            os.close(tmpFile)
            shutil.move(tmpFileName, targetFile)
            
    def getRunEnvironment(self, *args, **kw):
        self.environment.diag.info("Reading cached environment for " + repr(self))
        return self.environment.getValues(*args, **kw)

    def getIndent(self):
        relPath = self.getRelPath()
        if not len(relPath):
            return ""
        dirCount = string.count(relPath, "/") + 1
        return " " * (dirCount * 2)

    def testCaseList(self, filters=[]):
        if self.isAcceptedByAll(filters):
            return [ self ]
        else:
            return []

    def isAcceptedByAll(self, filters, checkContents=True):
        for filter in filters:
            if not self.isAcceptedBy(filter, checkContents):
                self.diagnose("Rejected due to " + repr(filter))
                return False
        return True

    def allTestsAndSuites(self):
        return [ self ]

    def size(self):
        return 1

    def refreshFiles(self):
        self.dircache.refresh()

    def filesChanged(self):
        self.refreshFiles()
        self.notify("FileChange")

    def refresh(self, *args):
        self.refreshFiles()
        self.notify("FileChange")


class TestCase(Test):
    def __init__(self, name, description, abspath, app, parent):
        Test.__init__(self, name, description, abspath, app, parent)
        # Directory where test executes from and hopefully where all its files end up
        self.writeDirectory = os.path.join(app.writeDirectory, app.name + app.versionSuffix(), self.getRelPath())

    def classId(self):
        return "test-case"
    
    def getDirectory(self, temporary=False, forFramework=False):
        if temporary:
            if forFramework:
                return os.path.join(self.writeDirectory, "framework_tmp")
            else:
                return self.writeDirectory
        else:
            return self.dircache.dir
            
    def changeState(self, state):
        isCompletion = not self.state.isComplete() and state.isComplete()
        self.state = state
        self.diagnose("Change notified to state " + state.category)
        if state and state.lifecycleChange:
            self.sendStateNotify(isCompletion)

    def sendStateNotify(self, isCompletion):
        notifyMethod = self.getNotifyMethod(isCompletion)
        notifyMethod("LifecycleChange", self.state, self.state.lifecycleChange)
        if self.state.lifecycleChange == "complete":
            notifyMethod("Complete")

    def getNotifyMethod(self, isCompletion):
        if isCompletion:
            return self.notifyThreaded # use the idle handlers to avoid things in the wrong order
        else:
            # might as well do it instantly if the test isn't still "active"
            return self.notify

    def actionsCompleted(self):
        self.diagnose("All actions completed")
        if self.state.isComplete():
            if not self.state.lifecycleChange:
                self.diagnose("Completion notified")
                self.state.lifecycleChange = "complete"
                self.sendStateNotify(True)
        else:
            self.notify("Complete")

    def getStateFile(self):
        return self.makeTmpFileName("teststate", forFramework=True)

    def makeWriteDirectory(self):
        self.diagnose("Created writedir at " + self.writeDirectory)
        plugins.ensureDirectoryExists(self.writeDirectory)
        frameworkTmp = self.getDirectory(temporary=1, forFramework=True)
        plugins.ensureDirectoryExists(frameworkTmp)

    def getOptionsFromFile(self, optionsFile):
        lines = plugins.readList(optionsFile)
        if len(lines) > 0:
            text = " ".join(lines)
            return string.Template(text).safe_substitute(self.environment)
        else:
            return ""

    def removeOptions(self, optionArgs, toClear):
        # Only want to remove them as a sequence
        try:
            pos = optionArgs.index(toClear[0])
        except ValueError:
            return
        
        for itemToClear in toClear:
            if itemToClear == optionArgs[pos]:
                del optionArgs[pos]
                # which should leave the new pos as the next item

    def getInterpreterOptions(self):
        return self.getCommandLineOptions(stem="interpreter_options")
        
    def getCommandLineOptions(self, stem="options"):
        optionArgs = []
        for optionsFile in self.getAllPathNames(stem):
            optionString = self.getOptionsFromFile(optionsFile)
            if "{CLEAR}" in optionString: # wipes all other definitions
                optionArgs = []
                optionString = optionString.replace("{CLEAR}", "")
            else:
                startPos = optionString.find("{CLEAR ")
                if startPos != -1:
                    endPos = optionString.find("}", startPos)
                    clearStr = optionString[startPos:endPos + 1]
                    optionString = optionString.replace(clearStr, "")
                    self.removeOptions(optionArgs, plugins.splitcmd(clearStr[7:-1]))
            newArgs = plugins.splitcmd(optionString)
            if len(optionArgs) == 0:
                optionArgs = newArgs
            else:
                self.combineOptions(optionArgs, newArgs)

        return optionArgs

    def combineOptions(self, optionArgs, newArgs):
        prevOption = False
        optionInsertPos = self.findOptionInsertPosition(optionArgs)
        self.diagnose("Inserting options into " + repr(optionArgs) + " in position " + repr(optionInsertPos))
        for newArg in newArgs:
            if newArg.startswith("-") or prevOption:
                optionArgs.insert(optionInsertPos, newArg)
                optionInsertPos += 1
            else:
                optionArgs.append(newArg)
                optionInsertPos = len(optionArgs)
            prevOption = newArg.startswith("-")

    def findLastOptionIndex(self, optionArgs):
        for i, option in enumerate(reversed(optionArgs)):
            if option.startswith("-"):
                return len(optionArgs) - i - 1

    def findOptionInsertPosition(self, optionArgs):
        lastOptionIndex = self.findLastOptionIndex(optionArgs)
        if lastOptionIndex is None:
            return 0 # all positional, insert options at the beginning

        # We allow one non-option after the last one in case it's an argument
        return min(lastOptionIndex + 2, len(optionArgs))
        
    def listTmpFiles(self):
        tmpFiles = []
        if not os.path.isdir(self.writeDirectory):
            return tmpFiles
        filelist = os.listdir(self.writeDirectory)
        filelist.sort()
        for file in filelist:
            if file.endswith("." + self.app.name):
                tmpFiles.append(os.path.join(self.writeDirectory, file))
        return tmpFiles

    def listUnownedTmpPaths(self):
        paths = []
        filelist = os.listdir(self.writeDirectory)
        filelist.sort()
        for file in filelist:
            if file in [ "framework_tmp", "file_edits", "traffic_intercepts" ] or file.endswith("." + self.app.name):
                continue
            fullPath = os.path.join(self.writeDirectory, file)
            paths += self.listFiles(fullPath, file, followLinks=False)
        return paths

    def makeTmpFileName(self, stem, forComparison=1, forFramework=0):
        dir = self.getDirectory(temporary=1, forFramework=forFramework)
        if forComparison and not forFramework and stem.find(os.sep) == -1:
            return os.path.join(dir, stem + "." + self.app.name)
        else:
            return os.path.join(dir, stem)

    def makeBackupFileName(self, number):
        return self.makeTmpFileName("backup.previous." + str(number), forFramework=1)

    def getNewState(self, file, **updateArgs):
        try:
            # Would like to do load(file) here... but it doesn't work with universal line endings, see Python bug 1724366
            # http://sourceforge.net/tracker/index.php?func=detail&aid=1724366&group_id=5470&atid=105470
            newState = loads(file.read())
            newState.updateAfterLoad(self.app, **updateArgs)
            return True, newState
        except (UnpicklingError, ImportError, EOFError, AttributeError):
            return False, plugins.Unrunnable(briefText="read error", \
                                             freeText="Failed to read results file")
    def saveState(self):
        stateFile = self.getStateFile()
        if os.path.isfile(stateFile):
            # Don't overwrite previous saved state
            return

        file = plugins.openForWrite(stateFile)
        pickler = Pickler(file)
        pickler.dump(self.state)
        file.close()

    def isAcceptedBy(self, filter, *args):
        return filter.acceptsTestCase(self)

    def createPropertiesFiles(self):
        self.environment.checkPopulated()
        for var, value in self.properties.items():
            propFileName = self.makeTmpFileName(var + ".properties", forComparison=0)
            file = open(propFileName, "w")
            for subVar, subValue in value.items():
                file.write(subVar + " = " + subValue + "\n")


# class for caching and managing changes to test suite files
class TestSuiteFileHandler:
    def __init__(self):
        self.cache = {}

    def readWithWarnings(self, fileName, ignoreCache=False, filterMethod=None):
        if not ignoreCache:
            cached = self.cache.get(fileName)
            if cached is not None:
                return cached, OrderedDict()

        goodTests, badTests = plugins.readListWithComments(fileName, plugins.Callable(self.getExclusionReasons, filterMethod))
        self.cache[fileName] = goodTests
        return goodTests, badTests

    def read(self, *args, **kw):
        return self.readWithWarnings(*args, **kw)[0]

    def getExclusionReasons(self, testName, existingTestNames, fileName, filterMethod):
        if existingTestNames.has_key(testName):
            return "repeated inclusion of the same test name", "The test " + testName + \
                   " was included several times in a test suite file.\n" + \
                   "Please check the file at " + fileName
        if filterMethod and not filterMethod(testName):
            return "no test directory being found", \
                   "The test " + testName + " could not be found.\nPlease check the file at " + fileName
        return "", ""

    def write(self, fileName, content):
        testEntries = self.makeWriteEntries(content)
        output = "\n".join(testEntries)
        if not output.endswith("\n"):
            output += "\n"
        newFile = plugins.openForWrite(fileName)
        newFile.write(output.lstrip())
        newFile.close()

    def makeWriteEntries(self, content):
        entries = []
        for testName, comment in content.items():
            entries.append(self.testOutput(testName, comment))
        return entries

    def testOutput(self, testName, comment):
        if len(comment) == 0:
            return testName
        else:
            return "\n# " + comment.replace("\n", "\n# ").replace("# __EMPTYLINE__", "") + "\n" + testName

    def add(self, fileName, *args):
        cache = self.read(fileName)
        self.addToCache(fileName, cache, *args)
        
    def addToCache(self, fileName, cache, testName, description, index):
        cacheList = cache.items()
        cacheList.insert(index, (testName, description))
        newCache = OrderedDict(cacheList)
        self.cache[fileName] = newCache
        self.write(fileName, newCache)
    
    def remove(self, fileName, testName):
        cache = self.read(fileName)
        description = self.removeFromCache(cache, testName)[0]
        if description is not None:
            self.write(fileName, cache)

    def removeFromCache(self, cache, testName):
        description = cache.get(testName)
        if description is not None:
            index = cache.keys().index(testName)
            del cache[testName]
            return description, index
        else:
            return None, None

    def rename(self, fileName, oldName, newName, newDescription):
        cache = self.read(fileName)
        description, index = self.removeFromCache(cache, oldName)
        if description is None:
            return False

        # intended to preserve comments that aren't tied to a test
        descToUse = plugins.replaceComment(description, newDescription)
        self.addToCache(fileName, cache, newName, descToUse, index)
        return True

    def reposition(self, fileName, testName, newIndex):
        cache = self.read(fileName)
        description = self.removeFromCache(cache, testName)[0]
        if description is None:
            return False

        self.addToCache(fileName, cache, testName, description, newIndex)
        return True

    def sort(self, fileName, comparator):
        tests = self.read(fileName)
        newDict = OrderedDict()
        for testName in sorted(tests.keys(), comparator):
            newDict[testName] = tests[testName]
        self.cache[fileName] = newDict
        self.write(fileName, newDict)


class TestSuite(Test):
    testSuiteFileHandler = TestSuiteFileHandler()
    def __init__(self, name, description, dircache, app, parent=None):
        Test.__init__(self, name, description, dircache, app, parent)
        self.testcases = []
        contentFile = self.getContentFileName()
        if not contentFile:
            self.createContentFile()
        self.autoSortOrder = self.getConfigValue("auto_sort_test_suites")
    
    def readContents(self, filters=[], initial=True):
        testNames, badTestNames = self.readTestNamesWithWarnings()
        self.createTestCases(filters, testNames, initial)
        if self.isEmpty() and len(testNames) > 0:
            # If the contents are filtered away, don't include the suite
            return False

        # Only print warnings if the test would otherwise have been accepted
        for testName, warningText in badTestNames.items():
            dirCache = self.createTestCache(testName)
            className = self.getSubtestClass(dirCache)
            subTest = self.createSubtest(testName, "", dirCache, className)
            if subTest.isAcceptedByAll(filters, checkContents=False):
                plugins.printWarning(warningText)

        for filter in filters:
            if not filter.acceptsTestSuiteContents(self):
                self.diagnose("Contents rejected due to " + repr(filter))
                return False
        return True

    def readTestNamesWithWarnings(self, ignoreCache=False):
        fileName = self.getContentFileName()
        if fileName:
            return self.testSuiteFileHandler.readWithWarnings(fileName, ignoreCache, self.fileExists)
        else:
            return OrderedDict(), OrderedDict()

    def readTestNames(self, ignoreCache=False):
        return self.readTestNamesWithWarnings(ignoreCache)[0]

    def findTestCases(self, version):
        versionFile = self.getFileName("testsuite", version)
        newTestNames = self.testSuiteFileHandler.read(versionFile)
        newTestList = []
        for testCase in self.testcases:
            if testCase.name in newTestNames:
                newTestList.append(testCase)
        return newTestList

    def fileExists(self, name):
        return self.dircache.exists(name)

    def testCaseList(self, filters=[]):
        list = []
        if not self.isAcceptedByAll(filters):
            return list
        for case in self.testcases:
            list += case.testCaseList(filters)
        return list

    def allTestsAndSuites(self):
        result = [ self ]
        for test in self.testcases:
            result += test.allTestsAndSuites()
        return result

    def classId(self):
        return "test-suite"

    def isEmpty(self):
        return len(self.testcases) == 0

    def isAcceptedBy(self, filter, checkContents):
        return filter.acceptsTestSuite(self) and (not checkContents or filter.acceptsTestSuiteContents(self))

    def findTestSuiteFiles(self):
        contentFile = self.getContentFileName()
        versionFiles = []
        allFiles = self.app.getAllFileNames([ self.dircache ], "testsuite", allVersions=True)
        for newFile in allFiles:
            if newFile != contentFile:
                versionFiles.append(newFile)
        if contentFile:
            return [ contentFile ] + versionFiles
        else:
            return versionFiles # can happen when removing suites recursively
        
    def getContentFileName(self):
        return self.getFileName("testsuite")
    
    def createContentFile(self):
        contentFile = self.dircache.pathName("testsuite." + self.app.name)
        file = open(contentFile, "a")
        file.write("# Ordered list of tests in test suite. Add as appropriate\n\n")
        file.close()
        self.dircache.refresh()
        
    def contentChanged(self):
        # Here we assume that only order can change...
        self.refreshFiles()
        self.updateOrder()

    def updateAllRelPaths(self, origRelPath):
        Test.updateAllRelPaths(self, origRelPath)
        for subTest in self.testcases:
            subTest.updateAllRelPaths(os.path.join(origRelPath, subTest.name))

    def updateOrder(self):
        testNames = self.readTestNames().keys() # this is cached anyway
        testCaseNames = map(lambda l: l.name, filter(lambda l: l.classId() == "test-case", self.testcases))

        newList = []
        for testName in self.getOrderedTestNames(testNames, testCaseNames):
            for testcase in self.testcases:
                if testcase.name == testName:
                    newList.append(testcase)
                    break
        if newList != self.testcases:
            self.testcases = newList
            self.notify("ContentChange")
    def size(self):
        size = 0
        for testcase in self.testcases:
            size += testcase.size()
        return size
    def maxIndex(self):
        return len(self.testcases) - 1
    def refresh(self, filters):
        self.diagnose("refreshing!")
        Test.refresh(self, filters)
        newTestNames = self.readTestNames(ignoreCache=True)
        toRemove = filter(lambda test: test.name not in newTestNames, self.testcases)
        for test in toRemove:
            self.diagnose("removing " + repr(test))
            test.removeFromMemory()

        for testName, descStr in newTestNames.items():
            existingTest = self.findSubtest(testName)
            desc = plugins.extractComment(descStr)
            if existingTest:
                existingTest.setDescription(desc)
                existingTest.refresh(filters)
                testClass = self.getSubtestClass(existingTest.dircache)
                if existingTest.__class__ != testClass:
                    self.diagnose("changing type for " + repr(existingTest))
                    self.testcases.remove(existingTest)
                    existingTest.notify("Remove")
                    self.createTestOrSuite(testName, desc, existingTest.dircache, filters, initial=False)
            else:
                self.diagnose("creating new test called '" + testName + "'")
                dirCache = self.createTestCache(testName)
                self.createTestOrSuite(testName, desc, dirCache, filters, initial=False)
        self.updateOrder()

# private:
    def getOrderedTestNames(self, testNames, testCaseNames):
        if self.autoSortOrder == 0:
            return testNames
        elif self.autoSortOrder == 1:
            return sorted(testNames, lambda a, b: self.compareTests(True, testCaseNames, a, b))
        else:
            return sorted(testNames, lambda a, b: self.compareTests(False, testCaseNames, a, b))

    def createTestCases(self, filters, testNames, initial):
        testCaches = {}
        testCaseNames = []
        if self.autoSortOrder:
            for testName in testNames.keys():
                dircache = self.createTestCache(testName)
                testCaches[testName] = dircache
                if not dircache.hasStem("testsuite"):
                    testCaseNames.append(testName)

        for testName in self.getOrderedTestNames(testNames.keys(), testCaseNames):
            dirCache = testCaches.get(testName, self.createTestCache(testName))
            desc = plugins.extractComment(testNames.get(testName))
            self.createTestOrSuite(testName, desc, dirCache, filters, initial)

    def createTestOrSuite(self, testName, description, dirCache, filters, initial=True):
        className = self.getSubtestClass(dirCache)
        subTest = self.createSubtest(testName, description, dirCache, className)
        if subTest.isAcceptedByAll(filters, checkContents=False) and subTest.readContents(filters, initial):
            self.testcases.append(subTest)
            subTest.notify("Add", initial)

    def createTestCache(self, testName):
        return DirectoryCache(os.path.join(self.getDirectory(), testName))

    def getSubtestClass(self, cache):
        return TestSuite if cache.hasStem("testsuite." + self.app.name) else TestCase

    def createSubtest(self, testName, description, cache, className):
        test = className(testName, description, cache, self.app, self)
        test.setObservers(self.observers)
        return test

    def addTestCase(self, *args, **kwargs):
        return self.addTest(TestCase, *args, **kwargs)
    def addTestSuite(self, *args, **kwargs):
        return self.addTest(TestSuite, *args, **kwargs)
    def addTest(self, className, testName, description="", placement=-1, postProcFunc=None):
        cache = self.createTestCache(testName)
        test = self.createSubtest(testName, description, cache, className)
        if postProcFunc:
            postProcFunc(test)
        self.testcases.insert(placement, test)
        test.notify("Add", initial=False)
        return test
    def addTestCaseWithPath(self, testPath):
        pathElements = testPath.split("/", 1)
        subSuite = self.findSubtest(pathElements[0])
        if len(pathElements) == 1:
            # add it even if it already exists, then we get two of them :)
            return self.addTestCase(testPath)
        else:
            if not subSuite:
                subSuite = self.addTestSuite(pathElements[0])
            return subSuite.addTestCaseWithPath(pathElements[1])
    def findSubtestWithPath(self, testPath):
        if len(testPath) == 0:
            return self
        pathElements = testPath.split("/", 1)
        subTest = self.findSubtest(pathElements[0])
        if subTest:
            if len(pathElements) > 1:
                return subTest.findSubtestWithPath(pathElements[1])
            else:
                return subTest

    def findSubtest(self, testName):
        for test in self.testcases:
            if test.name == testName:
                return test
    def repositionTest(self, test, newIndex):
        # Find test in list
        testSuiteFileName = self.getContentFileName()
        if not self.testSuiteFileHandler.reposition(testSuiteFileName, test.name, newIndex):
            return False

        testNamesInOrder = self.readTestNames()
        newList = []
        for testName in testNamesInOrder.keys():
            test = self.findSubtest(testName)
            if test:
                newList.append(test)

        self.testcases = newList
        self.notify("ContentChange")
        return True
    def sortTests(self, ascending = True):
        # Get testsuite list, sort in the desired order. Test
        # cases always end up before suites, regardless of name.
        for testSuiteFileName in self.findTestSuiteFiles():
            testNames = map(lambda t: t.name, filter(lambda t: t.classId() == "test-case", self.testcases))
            comparator = lambda a, b: self.compareTests(ascending, testNames, a, b)
            self.testSuiteFileHandler.sort(testSuiteFileName, comparator)

        testNamesInOrder = self.readTestNames()
        newList = []
        for testName in testNamesInOrder.keys():
            for test in self.testcases:
                if test.name == testName:
                    newList.append(test)
                    break
        self.testcases = newList
        self.notify("ContentChange")
    def compareTests(self, ascending, testNames, a, b):
        if a in testNames:
            if b in testNames:
                if ascending:
                    return cmp(a.lower(), b.lower())
                else:
                    return cmp(b.lower(), a.lower())
            else:
                return -1
        else:
            if b in testNames:
                return 1
            else:
                if ascending:
                    return cmp(a.lower(), b.lower())
                else:
                    return cmp(b.lower(), a.lower())

    def changeDirectory(self, newDir, origRelPath):
        Test.changeDirectory(self, newDir, origRelPath)
        for test in self.testcases:
            testNewDir = os.path.join(newDir, test.name)
            testOrigRelPath = os.path.join(origRelPath, test.name)
            test.changeDirectory(testNewDir, testOrigRelPath)

    def registerTest(self, *args):
        self.testSuiteFileHandler.add(self.getContentFileName(), *args)

    def getFollower(self, test):
        try:
            position = self.testcases.index(test)
            return self.testcases[position + 1]
        except (ValueError, IndexError):
            pass

    def removeFromMemory(self):
        for test in self.testcases:
            test.notify("Remove")
        self.testcases = []
        Test.removeFromMemory(self)

    def removeFromTestFile(self, testName):
        # Remove from all versions, since we've removed the actual
        # test dir, it's useless to keep the test anywhere ...
        for contentFileName in self.findTestSuiteFiles():
            self.testSuiteFileHandler.remove(contentFileName, testName)


class BadConfigError(RuntimeError):
    pass

class ConfigurationCall:
    def __init__(self, name, app):
        self.name = name
        self.app = app
        self.firstAttemptException = ""
        self.targetCall = getattr(app.configObject, name)
    def __call__(self, *args, **kwargs):
        try:
            return self.targetCall(*args, **kwargs)
        except (TypeError, AttributeError):
            if self.firstAttemptException:
                self.raiseException()
            else:
                self.firstAttemptException = plugins.getExceptionString()
                return self(self.app, *args, **kwargs)
        except plugins.TextTestError:
            # Just pass it through here, these are deliberate
            raise
        except Exception:
            self.raiseException()
    def raiseException(self):
        message = "Exception thrown by '" + self.app.getConfigValue("config_module") + \
                  "' configuration, while requesting '" + self.name + "'"
        if self.firstAttemptException:
            sys.stderr.write("Both attempts to call configuration failed, both exceptions follow :\n")
            sys.stderr.write(self.firstAttemptException + "\n" + plugins.getExceptionString())
        else:
            plugins.printException()
        raise BadConfigError, message

class Application:
    def __init__(self, name, dircache, versions, inputOptions, configEntries={}):
        self.name = name
        self.dircache = dircache
        # Place to store reference to extra_version applications
        self.extras = []
        # Cache all environment files in the whole suite to stop constantly re-reading them
        self.envFiles = {}
        self.versions = versions
        self.diag = logging.getLogger("application")
        self.inputOptions = inputOptions
        self.configDir = plugins.MultiEntryDictionary(importKey="import_config_file", importFileFinder=self.configPath)
        self.setUpConfiguration(configEntries)
        self.checkSanity()
        self.writeDirectory = self.getWriteDirectory()
        self.rootTmpDir = os.path.dirname(self.writeDirectory)
        self.diag.info("Write directory at " + self.writeDirectory)
        self.checkout = self.configObject.setUpCheckout(self)
        self.diag.info("Checkout set to " + self.checkout)
        self.tmpSettingsDirCache = DirectoryCache(inputOptions.get("td")) if "td" in inputOptions else None
        
    def __repr__(self):
        return self.fullName() + self.versionSuffix()

    def __hash__(self):
        return id(self)

    def fullName(self):
        return self.getConfigValue("full_name")

    def getPersonalConfigFiles(self):
        includePersonal = self.inputOptions.configPathOptions()[1]
        if not includePersonal:
            return []
        else:
            dircache = DirectoryCache(plugins.getPersonalConfigDir())
            return self.getAllFileNames([ dircache ], "config")
        
    def setUpConfiguration(self, configEntries={}):
        self.configDir.clear()
        self.configDocs = {}
        self.defaultDirCaches = self.getDefaultDirCaches()
        self.extraDirCaches = {}
        self.setConfigDefaults()

        # Read our pre-existing config files
        self.readConfigFiles(configModuleInitialised=False)
        self.diag.info("Basic Config file settings are: " + "\n" + repr(self.configDir))
        self.diag.info("Found application '" + self.name + "'")
        self.configObject = self.makeConfigObject()
        # Fill in the values we expect from the configurations, and read the file a second time
        self.configObject.setApplicationDefaults(self)
        self.setDependentConfigDefaults()
        self.readConfigFiles(configModuleInitialised=True)
        if len(configEntries):
            # We've been given some entries, read them in and write them out to file
            self.importAndWriteEntries(configEntries)

        self.configDir.readValues(self.getPersonalConfigFiles(), insert=False, errorOnUnknown=False)
        self.diag.info("Config file settings are: " + "\n" + repr(self.configDir))
        if not plugins.TestState.showExecHosts:
            plugins.TestState.showExecHosts = self.configObject.showExecHostsInFailures(self)

    def reloadConfiguration(self):
        # Try to make this as atomic as possible, to avoid problems when other threads
        # are reading from these objects while this is going on
        tmpApp = Application(self.name, self.dircache, self.versions, self.inputOptions)
        self.configDir = tmpApp.configDir
        self.configObject = tmpApp.configObject
        self.extraDirCaches = tmpApp.extraDirCaches
        self.defaultDirCaches = tmpApp.defaultDirCaches
        self.configDocs = tmpApp.configDocs
        
    def importAndWriteEntries(self, configEntries):
        configFileName = self.dircache.pathName("config." + self.name)
        configFile = open(configFileName, "w")
        for key, value in configEntries.items():
            if key == "section_comment":
                configFile.write("## " + value.replace("\n", "\n## ") + "\n\n")
            else:
                configFile.write("# " + self.configDocs.get(key) + "\n")
                if isinstance(value, tuple):
                    subKey, subValue = value
                    self.importAndWriteSection(key, subKey, subValue, configFile)
                else:
                    self.importAndWriteEntry(key, value, configFile)

    def importAndWriteEntry(self, key, value, configFile):
        self.configDir.addEntry(key, value, insert=False, errorOnUnknown=True)
        configFile.write(key + ":" + value + "\n\n")

    def importAndWriteSection(self, sectionName, key, value, configFile):
        self.configDir.addEntry(key, value, sectionName, insert=False, errorOnUnknown=True)
        configFile.write("[" + sectionName + "]\n")
        configFile.write(key + ":" + value + "\n[end]\n")
        
    def makeExtraDirCache(self, envDir):
        if envDir == "":
            return

        if os.path.isabs(envDir) and os.path.isdir(envDir):
            return DirectoryCache(envDir)

        for rootDir in self.inputOptions.rootDirectories:
            rootPath = os.path.join(rootDir, envDir)
            if os.path.isdir(rootPath):
                return DirectoryCache(rootPath)
            
        appPath = os.path.join(self.getDirectory(), envDir)
        if os.path.isdir(appPath):
            return DirectoryCache(appPath)

    def getExtraDirCaches(self, fileName, includeRoot=False, **kwargs):
        dirCacheNames = self.getCompositeConfigValue("extra_search_directory", fileName, **kwargs)
        dirCacheNames.reverse() # lowest-priority comes first, so it can be overridden
        if includeRoot:
            dirCacheNames += self.inputOptions.rootDirectories
        dirCaches = []
        for dirName in dirCacheNames:
            if self.extraDirCaches.has_key(dirName):
                cached = self.extraDirCaches.get(dirName)
                if cached:
                    dirCaches.append(cached)
            else:
                dirCache = self.makeExtraDirCache(dirName)
                if dirCache:
                    self.extraDirCaches[dirName] = dirCache
                    dirCaches.append(dirCache)
                else:
                    self.extraDirCaches[dirName] = None # don't look for it again
        return dirCaches

    def makeConfigObject(self):
        moduleName = self.getConfigValue("config_module")
        if self.dircache.exists("texttest_config_modules"):
            # Allow config modules to be stored under the test suite
            sys.path.insert(0, self.dircache.pathName("texttest_config_modules"))
        try:
            return plugins.importAndCall(moduleName, "getConfig", self.inputOptions)
        except:
            if sys.exc_type == exceptions.ImportError:
                errorString = "No module named " + moduleName
                if str(sys.exc_value) == errorString:
                    raise BadConfigError, "could not find config_module " + repr(moduleName)
                elif str(sys.exc_value) == "cannot import name getConfig":
                    raise BadConfigError, "module " + repr(moduleName) + " is not intended for use as a config_module"
            plugins.printException()
            raise BadConfigError, "config_module " + repr(moduleName) + " contained errors and could not be imported"

    def __getattr__(self, name): # If we can't find a method, assume the configuration has got one
        if hasattr(self.configObject, name):
            return ConfigurationCall(name, self)
        else:
            raise AttributeError, "No such Application method : " + name

    def getDirectory(self):
        return self.dircache.dir

    def getRootDirectory(self):
        for rootDir in self.inputOptions.rootDirectories:
            if self.dircache.dir.startswith(rootDir):
                return rootDir

    def checkSanity(self):
        if not self.getConfigValue("executable"):
            raise BadConfigError, "config file entry 'executable' not defined"

    def getRunMachine(self):
        if self.inputOptions.has_key("m"):
            return plugins.interpretHostname(self.inputOptions["m"])
        else:
            return plugins.interpretHostname(self.getConfigValue("default_machine"))

    def readConfigFiles(self, configModuleInitialised):
        self.readDefaultConfigFiles()
        self.readExplicitConfigFiles(configModuleInitialised)

    def getDefaultDirCaches(self):
        includeSite, includePersonal = self.inputOptions.configPathOptions()
        return map(DirectoryCache, plugins.findDataDirs(includeSite, includePersonal))

    def readDefaultConfigFiles(self):
        # don't error check as there might be settings there for all sorts of config modules...
        self.readValues(self.configDir, "config", self.defaultDirCaches, insert=False, errorOnUnknown=False)
            
    def readExplicitConfigFiles(self, configModuleInitialised):
        prevFiles = []
        dependentsSetUp = False
        while True:
            dircaches = self.getExtraDirCaches("config") + [ self.dircache ]
            allFiles = self.getAllFileNames(dircaches, "config")
            if len(allFiles) == len(prevFiles):
                if configModuleInitialised and not dependentsSetUp and self.configObject.setDependentConfigDefaults(self):
                    dependentsSetUp = True
                else:
                    return
            else:
                self.diag.info("Reading explicit config files : " + "\n".join(allFiles))
                self.configDir.readValues(allFiles, insert=False, errorOnUnknown=configModuleInitialised)
                prevFiles = allFiles
        
    def readValues(self, multiEntryDict, stem, dircaches, insert=True, errorOnUnknown=False):
        allFiles = self.getAllFileNames(dircaches, stem)
        self.diag.info("Reading values for " + stem + " from files : " + "\n".join(allFiles))
        multiEntryDict.readValues(allFiles, insert, errorOnUnknown)

    def setEnvironment(self, test):
        test.environment.diag.info("Reading environment for " + repr(test))
        envFiles = test.getAllPathNames("environment")
        allVars = sum((self.readEnvironment(f) for f in envFiles), [])
        allProps = []
        for suite in test.getAllTestsToRoot():
            vars, props = self.configObject.getConfigEnvironment(suite)
            allVars += vars
            allProps += props

        test.environment.storeVariables(allVars)
        for var, value, propFile in allProps:
            test.addProperty(var, value, propFile)

    def readEnvironment(self, envFile):
        if self.envFiles.has_key(envFile):
            return self.envFiles[envFile]

        envDir = plugins.MultiEntryDictionary()
        envDir.readValues([ envFile ])
        envVars = envDir.items()
        self.envFiles[envFile] = envVars
        return envVars
    
    def configPath(self, fileName):
        if os.path.isabs(fileName):
            return fileName

        dirCaches = []
        dirCaches += self.defaultDirCaches
        dirCaches += self.getExtraDirCaches(fileName, includeRoot=True)
        dirCaches.append(self.dircache)
        configPath = self.getFileNameFromCaches(dirCaches, fileName)
        if not configPath:
            raise BadConfigError, "Cannot find file '" + fileName + "' to import config file settings from"
        return os.path.normpath(configPath)

    def getDataFileNames(self, test=None):
        confObj = test or self
        allNames = confObj.getConfigValue("link_test_path") + \
                   confObj.getConfigValue("copy_test_path") + \
                   confObj.getConfigValue("copy_test_path_merge") + \
                   confObj.getConfigValue("partial_copy_test_path")
        # Don't manage data that has an external path name, only accept absolute paths built by ourselves...
        return filter(self.isLocalDataFile, allNames)

    def isLocalDataFile(self, name):
        return name and (self.writeDirectory in name or not os.path.isabs(name))

    def defFileStems(self, category="all"):
        dict = self.getConfigValue("definition_file_stems")
        if category == "all":
            return dict.get("builtin") + dict.get("regenerate") + dict.get("default")
        else:
            return dict.get(category)

    def getFileName(self, dirList, stem):
        dircaches = map(DirectoryCache, dirList)
        return self.getFileNameFromCaches(dircaches, stem)

    def getFileNameFromCaches(self, dircaches, stem):
        allFiles = self.getAllFileNames(dircaches, stem)
        if len(allFiles):
            return allFiles[-1]

    def getAllFileNames(self, dircaches, stem, allVersions=False):
        versionPred = self.getExtensionPredicate(allVersions)
        versionSets = OrderedDict()
        for dircache in dircaches:
            # Sorts into order most specific first
            currVersionSets = dircache.findVersionSets(stem, versionPred)
            for vset, files in currVersionSets.items():
                versionSets.setdefault(vset, []).extend(files)

        if allVersions:
            sortedVersionSets = sorted(versionSets.keys(), self.compareForDisplay)
        else:
            sortedVersionSets = sorted(versionSets.keys(), self.compareForPriority)
        allFiles = []
        for vset in sortedVersionSets:
            allFiles += versionSets[vset]
        self.diag.info("Files for stem " + stem + " found " + repr(allFiles))
        return allFiles

    def getRefVersionApplication(self, refVersion):
        return Application(self.name, self.dircache, refVersion.split("."), self.inputOptions)
    def getPreviousWriteDirInfo(self, previousTmpInfo):
        # previousTmpInfo can be either a directory, which should be returned if it exists,
        # a user name, which should be expanded and checked
        if previousTmpInfo:
            previousTmpInfo = os.path.expanduser(previousTmpInfo)
        else:
            previousTmpInfo = self.rootTmpDir
        if os.path.isdir(previousTmpInfo):
            return previousTmpInfo
        else:
            # try as user name
            if previousTmpInfo.find("/") == -1 and previousTmpInfo.find("\\") == -1:
                return os.path.expanduser("~" + previousTmpInfo + "/.texttest/tmp")
            else:
                return previousTmpInfo
    def findOtherAppNames(self):
        names = set()
        for configFile in self.dircache.findAllFiles("config"):
            appName = os.path.basename(configFile).split(".")[1]
            if appName != self.name:
                names.add(appName)
        return names

    def setConfigDefaults(self):
        self.setConfigDefault("executable", "", "Full path to the System Under Test")
        self.setConfigAlias("binary", "executable")
        self.setConfigDefault("config_module", "default", "Configuration module to use")
        self.setConfigDefault("import_config_file", [], "Extra config files to use")
        self.setConfigDefault("full_name", self.name.upper(), "Expanded name to use for application")
        self.setConfigDefault("home_operating_system", "any", "Which OS the test results were originally collected on")
        self.setConfigDefault("base_version", { "default" : [] }, "Versions to inherit settings from")
        self.setConfigDefault("default_machine", "localhost", "Default machine to run tests on")
        self.setConfigDefault("kill_timeout", 0.0, "Number of (wall clock) seconds to wait before killing the test")
        self.setConfigDefault("kill_command", "taskkill /F /T /PID", "Kill command to use on non-posix machines")
        # various varieties of test data
        self.setConfigDefault("partial_copy_test_path", [], "Paths to be part-copied, part-linked to the sandbox")
        self.setConfigDefault("copy_test_path", [], "Paths to be copied to the sandbox when running tests")
        self.setConfigDefault("copy_test_path_merge", [], "Directories to be copied to the sandbox, and merged together")
        self.setConfigDefault("copy_test_path_script", { "default": ""}, "Script to use when copying data files, instead of straight copy")
        self.setConfigDefault("link_test_path", [], "Paths to be linked from the temp. directory when running tests")
        self.setConfigDefault("test_data_ignore", { "default" : [] }, \
                              "Elements under test data structures which should not be viewed or change-monitored")
        self.setConfigDefault("definition_file_stems", { "default": [], "builtin": [ "config", "environment", "testsuite" ]}, \
                              "files to be shown as definition files by the static GUI")
        self.setConfigDefault("unsaveable_version", [], "Versions which should not have results saved for them")
        self.setConfigDefault("version_priority", { "default": 99 }, \
                              "Mapping of version names to a priority order in case of conflict.")
        self.setConfigDefault("extra_search_directory", { "default" : [] }, "Additional directories to search for TextTest files")
        self.setConfigDefault("filename_convention_scheme", "classic", "Naming scheme to use for files for stdin,stdout and stderr")
        self.setConfigAlias("test_data_searchpath", "extra_search_directory")
        self.setConfigAlias("extra_config_directory", "extra_search_directory")

    def setDependentConfigDefaults(self):
        executable = self.getConfigValue("executable")
        # Set values which default to other values
        self.setConfigDefault("interactive_action_module", self.getConfigValue("config_module") + "_gui",
                              "Module to search for InteractiveActions for the GUI")
        self.setConfigDefault("interpreter", plugins.getInterpreter(executable), "Program to use as interpreter for the SUT")

    def getFullVersion(self, forSave = 0):
        versionsToUse = self.versions
        if forSave:
            versionsToUse = self.filterUnsaveable(self.versions)
            self.diag.info("Versions for saving = " + repr(versionsToUse) + " from " + repr(self.versions))
            if versionsToUse != self.versions:
                # Don't get implied base versions here, we don't want them to be the default save version
                saveableVersions = self.getSaveableVersions(baseVersionKey="default")
                saveableVersions.sort(lambda v1, v2: self.compareForPriority(set(v1.split(".")), set(v2.split("."))))
                self.diag.info("Saveable versions = " + repr(saveableVersions))
                if len(saveableVersions) == 0:
                    return ""
                else:
                    return saveableVersions[-1]
        return ".".join(versionsToUse)

    def versionSuffix(self):
        fullVersion = self.getFullVersion()
        if len(fullVersion) == 0:
            return ""
        return "." + fullVersion

    def makeTestSuite(self, responders, otherDir=None):
        if otherDir:
            dircache = DirectoryCache(otherDir)
        else:
            dircache = self.dircache
        suite = TestSuite(os.path.basename(dircache.dir), "Root test suite", dircache, self)
        suite.setObservers(responders)
        return suite

    def createInitialTestSuite(self, responders):
        suite = self.makeTestSuite(responders)
        # allow the configurations to decide whether to accept the application in the presence of
        # the suite's environment
        self.configObject.checkSanity(suite)
        return suite

    def createExtraTestSuite(self, filters=[], responders=[], otherDir=None):
        suite = self.makeTestSuite(responders, otherDir)
        suite.readContents(filters)
        return suite

    def description(self, includeCheckout = False):
        description = "Application " + self.fullName()
        if len(self.versions):
            description += ", version " + ".".join(self.versions)
        if includeCheckout and self.checkout:
            description += ", checkout " + self.checkout
        return description

    def rejectionMessage(self, message):
        return "Rejected " + self.description() + " - " + str(message) + "\n"

    def filterUnsaveable(self, versions):
        unsaveableVersions = self.getConfigValue("unsaveable_version")
        return filter(lambda v: v not in unsaveableVersions, versions)

    def getBaseVersions(self, baseVersionKey="implied"):
        # By default, this gets all names in base_version, not just those marked
        # "implied"! (it will also pick up "default").
        # To get only "default", this has to be provided by the caller
        return self.getCompositeConfigValue("base_version", baseVersionKey)

    def getExtensionPredicate(self, allVersions):
        if allVersions:
            # everything that has at least the given extensions
            return set([ self.name ]).issubset
        else:
            possVersions = [ self.name ] + self.getBaseVersions() + self.versions
            return set(possVersions).issuperset

    def compareForDisplay(self, vset1, vset2):
        if vset1.issubset(vset2):
            return -1
        elif vset2.issubset(vset1):
            return 1

        extraVersions = self.getExtraVersions()
        extraIndex1 = self.extraVersionIndex(vset1, extraVersions)
        extraIndex2 = self.extraVersionIndex(vset2, extraVersions)
        return cmp(extraIndex1, extraIndex2)

    def extraVersionIndex(self, vset, extraVersions):
        for version in vset:
            if version in extraVersions:
                return extraVersions.index(version)
        return 99
    
    def compareForPriority(self, vset1, vset2):
        versionSet = set(self.versions)
        self.diag.info("Compare " + repr(vset1) + " to " + repr(vset2))
        if len(versionSet) > 0:
            if vset1.issuperset(versionSet):
                return 1
            elif vset2.issuperset(versionSet):
                return -1

        explicitVersions = set([ self.name ] + self.versions)
        priority1 = self.getVersionSetPriority(vset1)
        priority2 = self.getVersionSetPriority(vset2)
        # Low number implies higher priority...
        if priority1 != priority2:
            self.diag.info("Version priority " + repr(priority1) + " vs " + repr(priority2))
            return cmp(priority2, priority1)

        versionCount1 = len(vset1.intersection(explicitVersions))
        versionCount2 = len(vset2.intersection(explicitVersions))
        if versionCount1 != versionCount2:
            # More explicit versions implies higher priority
            self.diag.info("Version count " + repr(versionCount1) + " vs " + repr(versionCount2))
            return cmp(versionCount1, versionCount2)

        baseVersions = set(self.getBaseVersions())
        baseCount1 = len(vset1.intersection(baseVersions))
        baseCount2 = len(vset2.intersection(baseVersions))
        self.diag.info("Base count " + repr(baseCount1) + " vs " + repr(baseCount2))
        # More base versions implies higher priority
        return cmp(baseCount1, baseCount2)

    def getVersionSetPriority(self, vlist):
        if len(vlist) == 0:
            return 99
        else:
            return min(map(self.getVersionPriority, vlist))

    def getVersionPriority(self, version):
        return self.getCompositeConfigValue("version_priority", version)

    def getSaveableVersions(self, **kw):
        versionsToUse = self.versions + self.getBaseVersions(**kw)
        versionsToUse = self.filterUnsaveable(versionsToUse)
        if len(versionsToUse) == 0:
            return []

        return self._getVersionExtensions(versionsToUse)

    def _getVersionExtensions(self, versions):
        if len(versions) == 1:
            return versions

        fullList = []
        current = versions[0]
        fromRemaining = self._getVersionExtensions(versions[1:])
        for item in fromRemaining:
            fullList.append(current + "." + item)
        fullList.append(current)
        fullList += fromRemaining
        return fullList

    def printHelpText(self):
        print helpIntro
        header = "Description of the " + self.getConfigValue("config_module") + " configuration"
        length = len(header)
        header += "\n" + "-" * length
        print header
        self.configObject.printHelpText()

    def getConfigValue(self, *args, **kw):
        return self.configDir.getSingle(*args, **kw)

    def getCompositeConfigValue(self, *args, **kw):
        return self.configDir.getComposite(*args, **kw)
       
    def addConfigEntry(self, key, value, sectionName = ""):
        self.configDir.addEntry(key, value, sectionName, insert=False, errorOnUnknown=True)

    def removeConfigEntry(self, key, value, sectionName = ""):
        self.configDir.removeEntry(key, value, sectionName)

    def setConfigDefault(self, key, value, docString = ""):
        self.configDir[key] = value
        if len(docString) > 0:
            self.configDocs[key] = docString

    def setConfigAlias(self, aliasName, realName):
        self.configDir.setAlias(aliasName, realName)


class OptionFinder(plugins.OptionFinder):
    def __init__(self):
        # Note: the comments in this method will be extracted for documenting environment variables!
        plugins.OptionFinder.__init__(self, sys.argv[1:])
        self.setPathFromOptionsOrEnv("TEXTTEST_HOME", ".", "d") # Alias for TEXTTEST_PATH
        textTestPath = self.getPathFromOptionsOrEnv("TEXTTEST_PATH", "$TEXTTEST_HOME") # Root directories of the test suite
        self.rootDirectories = textTestPath.split(os.pathsep)
        self.setPathFromOptionsOrEnv("STORYTEXT_HOME", "$TEXTTEST_HOME/storytext") # Location to store shortcuts from the GUI
        
        self.setPathFromOptionsOrEnv("TEXTTEST_PERSONAL_CONFIG", "~/.texttest") # Location of personal configuration
        self.diagWriteDir = self.setPathFromOptionsOrEnv("TEXTTEST_PERSONAL_LOG", "$TEXTTEST_PERSONAL_CONFIG/log", "xw") # Location to write TextTest's internal logs
        self.diagConfigFile = None
        if self.has_key("x"): # This is just a fast-track to make sure we can set up diags for the setup
            self.diagConfigFile = self.normalisePath(self.get("xr", os.path.join(self.diagWriteDir, "logging.debug")))
            self.setUpLogging()
        self.diag = logging.getLogger("option finder")
        self.diag.info("Replaying from " + repr(os.getenv("USECASE_REPLAY_SCRIPT")))
        self.diag.info(repr(self))

    def setPathFromOptionsOrEnv(self, envVar, *args):
        givenValue = self.getPathFromOptionsOrEnv(envVar, *args)
        if givenValue is not None:
            value = self.normalisePath(givenValue)
            os.environ[envVar] = value
            return value

    def normalisePath(self, path):
        return os.path.normpath(plugins.abspath(os.path.expanduser(path)))

    def getPathFromOptionsOrEnv(self, envVar, defaultValue, optionName=""):
        if optionName and self.has_key(optionName):
            return self[optionName]
        else:
            return os.getenv(envVar, os.path.expandvars(defaultValue))

    def setUpLogging(self):
        if os.path.isfile(self.diagConfigFile):
            print "TextTest will write diagnostics in", self.diagWriteDir, "based on file at", self.diagConfigFile
        else:
            print "Could not find diagnostic file at", self.diagConfigFile, ": cannot run with diagnostics"
            self.diagConfigFile = None
            self.diagWriteDir = None

        if self.diagWriteDir:
            plugins.ensureDirectoryExists(self.diagWriteDir)
            for file in os.listdir(self.diagWriteDir):
                if file.endswith(".diag"):
                    os.remove(os.path.join(self.diagWriteDir, file))

        if self.diagConfigFile:
            plugins.configureLogging(self.diagConfigFile)

    def findVersionList(self):
        versionList = []
        versionStr = self.get("v", "") or ""
        for version in plugins.commasplit(versionStr):
            if version in versionList:
                plugins.printWarning("Same version '" + version + "' requested more than once, ignoring.", stdout=True)
            else:
                versionList.append(version)
        return versionList
    
    def findSelectedAppNames(self):
        if not self.has_key("a"):
            return {}

        apps = plugins.commasplit(self["a"])
        appDict = {}
        versionList = self.findVersionList()
        for app in apps:
            parts = app.split(".", 1)
            appName = parts[0]
            appVersion = ""
            if len(parts) > 1:
                appVersion = parts[1]
            for version in versionList:
                self.addToAppDict(appDict, appName, self.combineVersions(version, appVersion))

        return appDict

    def combineVersions(self, v1, v2):
        if len(v1) == 0 or v1 == v2:
            return v2
        elif len(v2) == 0:
            return v1
        else:
            parts1 = v1.split(".")
            parts2 = v2.split(".")
            parts = parts1 + filter(lambda p: p not in parts1, parts2)
            return ".".join(parts)

    def addToAppDict(self, appDict, appName, versionName):
        versions = appDict.setdefault(appName, [])
        if versionName not in versions:
            versions.append(versionName)

    def helpMode(self):
        return self.has_key("help")

    def runScript(self):
        return self.get("s")

    def getScriptObject(self):
        script = self.runScript()
        if not script:
            return
        
        words = script.split(" ")
        actionCmd = words[0]
        actionArgs = words[1:] 
        if "." in actionCmd:
            return self._getScriptObject(actionCmd, actionArgs)
        else:
            raise plugins.TextTestError, "Plugin scripts must be of the form <module_name>.<script>\n"

    def _getScriptObject(self, actionCmd, actionArgs):
        module, className = actionCmd.rsplit(".", 1)
        importCommand = "from " + module + " import " + className + " as _class"
        try:
            exec importCommand
        except:
            # Backwards compatibility : many scripts are now in the default package
            excString = plugins.getExceptionString()
            if not module.startswith("default"):
                try:
                    return self._getScriptObject("default." + actionCmd, actionArgs)
                except plugins.TextTestError:
                    pass
            raise plugins.TextTestError, "Could not import script " + className + " from module " + module + "\n" +\
                  "Import failed, looked at " + repr(sys.path) + "\n" + excString
        
        try:
            if len(actionArgs) > 0:
                return _class(actionArgs)
            else:
                return _class()
        except:
            raise plugins.TextTestError, "Could not instantiate script action " + repr(actionCmd) +\
                  " with arguments " + repr(actionArgs) + "\n" + plugins.getExceptionString()

    def configPathOptions(self):
        # Returns includeSite, includePersonal
        if not self.has_key("vanilla"):
            return True, True

        vanilla = self.get("vanilla")
        if vanilla == "site":
            return False, True
        elif vanilla == "personal":
            return True, False
        else:
            return False, False
    

# Simple responder that collects completion notifications and sends one out when
# it thinks everything is done.
class AllCompleteResponder(plugins.Responder,plugins.Observable):
    def __init__(self, *args):
        plugins.Responder.__init__(self)
        plugins.Observable.__init__(self)
        self.unfinishedTests = 0
        self.lock = Lock()
        self.checkInCompletion = False
        self.hadCompletion = False
        self.diag = logging.getLogger("test objects")
        
    def notifyAdd(self, test, *args, **kw):
        if test.classId() == "test-case":
            # Locking long thought to be unnecessary
            # but += 1 is not an atomic operation!!
            # a = a + 1 and a = a - 1 from different threads do not guarantee "a" unchanged.
            self.lock.acquire()
            self.unfinishedTests += 1
            self.lock.release()
    def notifyAllRead(self, *args):
        self.lock.acquire()
        if self.unfinishedTests == 0 and self.hadCompletion:
            self.diag.info("All read -> notifying all complete")
            self.notify("AllComplete")
        else:
            self.checkInCompletion = True
        self.lock.release()
    def notifyComplete(self, test):
        self.diag.info("Complete " + str(self.unfinishedTests))
        self.lock.acquire()
        self.unfinishedTests -= 1
        if self.checkInCompletion and self.unfinishedTests == 0:
            self.diag.info("Final test read -> notifying all complete")
            self.notify("AllComplete")
        self.hadCompletion = True
        self.lock.release()

