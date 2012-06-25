
""" The default configuration, from which all others should be derived """

import os, plugins, sandbox, console, rundependent, comparetest, batch, performance, subprocess, operator, logging

from copy import copy
from string import Template
from fnmatch import fnmatch
# For back-compatibility
from runtest import RunTest, Running, Killed
from scripts import *

def getConfig(optionMap):
    return Config(optionMap)

class Config:
    loggingSetup = False
    def __init__(self, optionMap):
        self.optionMap = optionMap
        self.filterFileMap = {}
        if self.hasExplicitInterface():
            self.trySetUpLogging()
        from reconnect import ReconnectConfig
        self.reconnectConfig = ReconnectConfig(optionMap)

    def getMachineNameForDisplay(self, machine):
        return machine # override for queuesystems

    def getCheckoutLabel(self):
        return "Use checkout"

    def getMachineLabel(self):
        return "Run on machine"

    def addToOptionGroups(self, apps, groups):
        recordsUseCases = len(apps) == 0 or self.anyAppHas(apps, lambda app: app.getConfigValue("use_case_record_mode") != "disabled")
        useCatalogues = self.anyAppHas(apps, self.isolatesDataUsingCatalogues)
        useCaptureMock = self.anyAppHas(apps, self.usesCaptureMock)
        for group in groups:
            if group.name.startswith("Select"):
                group.addOption("t", "Test names containing", description="Select tests for which the name contains the entered text. The text can be a regular expression.")
                group.addOption("ts", "Test paths containing", description="Select tests for which the full path to the test (e.g. suite1/subsuite/testname) contains the entered text. The text can be a regular expression. You can select tests by suite name this way.")
                possibleDirs = self.getFilterFileDirectories(apps, useOwnTmpDir=True)
                group.addOption("f", "Tests listed in file", possibleDirs=possibleDirs, selectFile=True)
                group.addOption("desc", "Descriptions containing", description="Select tests for which the description (comment) matches the entered text. The text can be a regular expression.")
                if self.anyAppHas(apps, self.hasPerformance):
                    group.addOption("r", "Execution time", description="Specify execution time limits, either as '<min>,<max>', or as a list of comma-separated expressions, such as >=0:45,<=1:00. Digit-only numbers are interpreted as minutes, while colon-separated numbers are interpreted as hours:minutes:seconds.")
                group.addOption("grep", "Test-files containing", description="Select tests which have a file containing the entered text. The text can be a regular expression : e.g. enter '.*' to only look for the file without checking the contents.")
                group.addOption("grepfile", "Test-file to search", allocateNofValues=2, description="When the 'test-files containing' field is non-empty, apply the search in files with the given stem. Unix-style file expansion (note not regular expressions) may be used. For example '*' will look in any file.")
            elif group.name.startswith("Basic"):
                if len(apps) > 0:
                    version = plugins.getAggregateString(apps, lambda app: app.getFullVersion())
                    checkout = plugins.getAggregateString(apps, lambda app: app.checkout)
                    machine = plugins.getAggregateString(apps, lambda app: app.getRunMachine())
                else:
                    version, checkout, machine = "", "", ""
                group.addOption("v", "Run this version", version)
                group.addOption("c", self.getCheckoutLabel(), checkout)
                group.addOption("m", self.getMachineLabel(), self.getMachineNameForDisplay(machine))
                group.addOption("cp", "Times to run", 1, description="Set this to some number larger than 1 to run the same test multiple times, for example to try to catch indeterminism in the system under test")
                self.addDefaultSwitch(group, "stop", "Stop after first failure")
                if recordsUseCases:
                    self.addDefaultSwitch(group, "actrep", "Run with slow motion replay")
                if useCatalogues:
                    self.addDefaultSwitch(group, "ignorecat", "Ignore catalogue file when isolating data")
                if useCaptureMock:
                    self.addCaptureMockSwitch(group)
            elif group.name.startswith("Advanced"):
                self.addDefaultOption(group, "b", "Run batch mode session")
                self.addDefaultOption(group, "name", "Name this run")
                group.addOption("vanilla", "Ignore configuration files", self.defaultVanillaValue(),
                                possibleValues = [ "", "site", "personal", "all" ])
                self.addDefaultSwitch(group, "keeptmp", "Keep temporary write-directories")
                group.addSwitch("ignorefilters", "Ignore all run-dependent text filtering")
            elif group.name.startswith("Self-diagnostics"):
                self.addDefaultSwitch(group, "x", "Enable self-diagnostics")
                defaultDiagDir = plugins.getPersonalDir("log")
                group.addOption("xr", "Configure self-diagnostics from", os.path.join(defaultDiagDir, "logging.debug"),
                                possibleValues=[ os.path.join(plugins.installationDir("log"), "logging.debug") ])
                group.addOption("xw", "Write self-diagnostics to", defaultDiagDir)
            elif group.name.startswith("Invisible"):
                # Options that don't make sense with the GUI should be invisible there...
                group.addOption("a", "Load test applications named")
                group.addOption("s", "Run this script")
                group.addOption("d", "Look for test files under")
                group.addSwitch("help", "Print configuration help text on stdout")
                group.addSwitch("g", "use dynamic GUI")
                group.addSwitch("gx", "use static GUI")
                group.addSwitch("con", "use console interface")
                group.addSwitch("coll", "Collect results for batch mode session")
                group.addOption("tp", "Private: Tests with exact path") # use for internal communication
                group.addOption("finverse", "Tests not listed in file")
                group.addOption("fintersect", "Tests in all files")
                group.addOption("funion", "Tests in any of files")
                group.addOption("fd", "Private: Directory to search for filter files in")
                group.addOption("td", "Private: Directory to search for temporary settings in")
                group.addOption("count", "Private: How many tests we believe there will be")
                group.addOption("o", "Overwrite failures, optionally using version")
                group.addOption("reconnect", "Reconnect to previous run")
                group.addSwitch("reconnfull", "Recompute file filters when reconnecting", options=self.getReconnFullOptions())
                group.addSwitch("n", "Create new results files (overwrite everything)")
                group.addSwitch("new", "Start static GUI with no applications loaded")
                group.addOption("bx", "Select tests exactly as for batch mode session")
                group.addSwitch("zen", "Make console output coloured, for use e.g. with ZenTest")
                if recordsUseCases:
                    group.addSwitch("record", "Private: Record usecase rather than replay what is present")
                    group.addSwitch("autoreplay", "Private: Used to flag that the run has been autogenerated")
                else:
                    # We may have other apps that do this, don't reject these options
                    group.addSwitch("actrep", "Run with slow motion replay")
                if not useCatalogues:
                    group.addSwitch("ignorecat", "Ignore catalogue file when isolating data")
                if not useCaptureMock:
                    self.addCaptureMockSwitch(group)

    def addDefaultSwitch(self, group, key, name, *args, **kw):
        group.addSwitch(key, name, self.optionIntValue(key), *args, **kw)

    def addDefaultOption(self, group, key, name, *args, **kw):
        group.addOption(key, name, self.optionValue(key), *args, **kw)

    def addCaptureMockSwitch(self, group, value=0):
        options = [ "Replay", "Record", "Mixed Mode", "Disabled"  ]
        descriptions = [ "Replay all existing interactions from the information in CaptureMock's mock files. Do not record anything new.",
                         "Ignore any existing CaptureMock files and record all the interactions afresh.",
                         "Replay all existing interactions from the information in the CaptureMock mock files. " + \
                         "Record any other interactions that occur.",
                         "Disable CaptureMock" ]
        group.addSwitch("rectraffic", "CaptureMock", value=value, options=options, description=descriptions)

    def getReconnFullOptions(self):
        return ["Display results exactly as they were in the original run",
                "Use raw data from the original run, but recompute run-dependent text, known bug information etc."]

    def anyAppHas(self, apps, propertyMethod):
        for app in apps:
            for partApp in [ app ] + app.extras:
                if propertyMethod(partApp):
                    return True
        return False

    def defaultVanillaValue(self):
        if not self.optionMap.has_key("vanilla"):
            return ""
        given = self.optionValue("vanilla")
        return given or "all"

    def getRunningGroupNames(self):
        return [ ("Basic", None, None), ("Self-diagnostics (internal logging)", "x", 0), ("Advanced", None, None) ]

    def getAllRunningGroupNames(self, allApps):
        if len(allApps) == 0:
            return self.getRunningGroupNames()
        
        names = []
        for app in allApps:
            for name in app.getRunningGroupNames():
                if name not in names:
                    names.append(name)
        return names

    def createOptionGroups(self, allApps):
        groupNames = [ "Selection", "Invisible" ] + [ x[0] for x in self.getAllRunningGroupNames(allApps) ]
        optionGroups = map(plugins.OptionGroup, groupNames)
        self.addToOptionGroups(allApps, optionGroups)
        return optionGroups
    
    def findAllValidOptions(self, allApps):
        groups = self.createOptionGroups(allApps)
        return reduce(operator.add, (g.keys() for g in groups), [])

    def getCollectSequence(self):
        arg = self.optionMap.get("coll")
        sequence = []
        if not arg or "web" not in arg:
            emailHandler = batch.CollectFiles()
            sequence.append(emailHandler)
        if not arg or arg == "web":
            summaryGenerator = batch.GenerateSummaryPage()
            sequence.append(summaryGenerator)
        return sequence

    def getActionSequence(self):
        if self.optionMap.has_key("coll"):
            return self.getCollectSequence()

        if self.isReconnecting():
            return self.getReconnectSequence()

        scriptObject = self.optionMap.getScriptObject()
        if scriptObject:
            if self.usesComparator(scriptObject):
                return [ self.getWriteDirectoryMaker(), scriptObject, comparetest.MakeComparisons(ignoreMissing=True,enableColor=self.optionMap.has_key("zen")) ]
            else:
                return [ scriptObject ]
        else:
            return self.getTestProcessor()

    def usesComparator(self, scriptObject):
        try:
            return scriptObject.usesComparator()
        except AttributeError:
            return False

    def useGUI(self):
        return self.optionMap.has_key("g") or self.optionMap.has_key("gx")

    def useStaticGUI(self, app):
        return self.optionMap.has_key("gx") or \
               (not self.hasExplicitInterface() and app.getConfigValue("default_interface") == "static_gui")

    def useConsole(self):
        return self.optionMap.has_key("con")

    def getExtraVersions(self, app):
        fromConfig = self.getExtraVersionsFromConfig(app)
        fromCmd = self.getExtraVersionsFromCmdLine(app, fromConfig)
        return self.createComposites(fromConfig, fromCmd)

    def createComposites(self, vlist1, vlist2):
        allVersions = copy(vlist1)        
        for v2 in vlist2:
            allVersions.append(v2)
            for v1 in vlist1:
                allVersions.append(v2 + "." + v1)

        return allVersions

    def getExtraVersionsFromCmdLine(self, app, fromConfig):
        if self.isReconnecting():
            return self.reconnectConfig.getExtraVersions(app, fromConfig)
        else:
            copyVersions = self.getCopyExtraVersions()
            checkoutVersions, _ = self.getCheckoutExtraVersions(app)
            # Generated automatically to be able to distinguish, don't save them
            for ver in copyVersions + checkoutVersions:
                app.addConfigEntry("unsaveable_version", ver)
            return self.createComposites(checkoutVersions, copyVersions)

    def getCopyExtraVersions(self):
        try:
            copyCount = int(self.optionMap.get("cp", 1))
        except TypeError:
            copyCount = 1
        return [ "copy_" + str(i) for i in range(1, copyCount) ]

    def makeParts(self, c):
        return c.replace("\\", "/").split("/")

    def versionNameFromCheckout(self, c, checkoutNames):
        checkoutParts = self.makeParts(c)
        for other in checkoutNames:
            if other != c:
                for otherPart in self.makeParts(other):
                    if otherPart in checkoutParts:
                        checkoutParts.remove(otherPart)
                
        return checkoutParts[-1].replace(".", "_")

    def getCheckoutExtraVersions(self, app):    
        checkoutNames = plugins.commasplit(self.optionValue("c"))
        if len(checkoutNames) > 1:
            expandedNames = [ self.expandCheckout(c, app) for c in checkoutNames ]
            extraCheckouts = expandedNames[1:]
            return [ self.versionNameFromCheckout(c, expandedNames) for c in extraCheckouts ], extraCheckouts
        else:
            return [], []

    def getBatchSession(self, app):
        return self.optionValue("b")

    def getBatchSessionForSelect(self, app):
        return self.getBatchSession(app) or self.optionMap.get("bx")
        
    def getExtraVersionsFromConfig(self, app):
        basic = app.getConfigValue("extra_version")
        batchSession = self.getBatchSessionForSelect(app)
        if batchSession is not None:
            for batchExtra in app.getCompositeConfigValue("batch_extra_version", batchSession):
                if batchExtra not in basic:
                    basic.append(batchExtra)
        if self.optionMap.has_key("count"):
            return [] # dynamic GUI started from static GUI, rely on it telling us what to load
        for extra in basic:
            if extra in app.versions:
                return []
        return basic

    def getDefaultInterface(self, allApps):
        if self.optionMap.has_key("s"):
            return "console"
        elif len(allApps) == 0 or self.optionMap.has_key("new"):
            return "static_gui"

        defaultIntf = None
        for app in allApps:
            appIntf = app.getConfigValue("default_interface")
            if defaultIntf and appIntf != defaultIntf:
                raise plugins.TextTestError, "Conflicting default interfaces for different applications - " + \
                      appIntf + " and " + defaultIntf
            defaultIntf = appIntf
        return defaultIntf

    def setDefaultInterface(self, allApps):
        mapping = { "static_gui" : "gx", "dynamic_gui": "g", "console": "con" }
        defaultInterface = self.getDefaultInterface(allApps)
        if mapping.has_key(defaultInterface):
            self.optionMap[mapping[defaultInterface]] = ""
        else:
            raise plugins.TextTestError, "Invalid value for default_interface '" + defaultInterface + "'"
        
    def hasExplicitInterface(self):
        return self.useGUI() or self.batchMode() or self.useConsole() or self.optionMap.has_key("o")

    def getLogfilePostfixes(self):
        if self.optionMap.has_key("x"):
            return [ "debug" ]
        elif self.optionMap.has_key("gx"):
            return [ "gui", "static_gui" ]
        elif self.optionMap.has_key("g"):
            return [ "gui", "dynamic_gui" ]
        elif self.batchMode():
            return [ "console", "batch" ]
        else:
            return [ "console" ]

    def trySetUpLogging(self):
        if not self.loggingSetup:
            self.setUpLogging()
            Config.loggingSetup = True
        
    def setUpLogging(self):
        filePatterns = [ "logging." + postfix for postfix in self.getLogfilePostfixes() ]
        includeSite, includePersonal = self.optionMap.configPathOptions()
        allPaths = plugins.findDataPaths(filePatterns, includeSite, includePersonal, dataDirName="log")
        if len(allPaths) > 0:
            plugins.configureLogging(allPaths[-1]) # Won't have any effect if we've already got a log file
        else:
            plugins.configureLogging()
            
    def getResponderClasses(self, allApps):
        # Global side effects first :)
        if not self.hasExplicitInterface():
            self.setDefaultInterface(allApps)
            self.trySetUpLogging()

        return self._getResponderClasses(allApps)

    def _getResponderClasses(self, allApps):
        classes = []        
        if not self.optionMap.has_key("gx"):
            if self.optionMap.has_key("new"):
                raise plugins.TextTestError, "'--new' option can only be provided with the static GUI"
            elif len(allApps) == 0:
                raise plugins.TextTestError, "Could not find any matching applications (files of the form config.<app>) under " + " or ".join(self.optionMap.rootDirectories)
            
        if self.useGUI():
            self.addGuiResponder(classes)
        else:
            classes.append(self.getTextDisplayResponderClass())

        if not self.optionMap.has_key("gx"):
            classes += self.getThreadActionClasses()
        
        if self.batchMode() and not self.optionMap.has_key("s"):
            if self.optionMap.has_key("coll"):
                if self.optionMap["coll"] != "mail": 
                    classes.append(self.getWebPageResponder())
            else:
                if self.optionValue("b") is None:
                    plugins.log.info("No batch session identifier provided, using 'default'")
                    self.optionMap["b"] = "default"
                if self.anyAppHas(allApps, lambda app: self.emailEnabled(app)):
                    classes.append(batch.EmailResponder)
                if self.anyAppHas(allApps, lambda app: self.getBatchConfigValue(app, "batch_junit_format") == "true"):
                    from batch.junitreport import JUnitResponder
                    classes.append(JUnitResponder)
                
        if os.name == "posix" and self.useVirtualDisplay():
            from virtualdisplay import VirtualDisplayResponder
            classes.append(VirtualDisplayResponder)
        if self.keepTemporaryDirectories():
            classes.append(self.getStateSaver())
        if not self.useGUI() and not self.batchMode():
            classes.append(self.getTextResponder())
        # At the end, so we've done the processing before we proceed
        from storytext_interface import ApplicationEventResponder
        classes.append(ApplicationEventResponder)
        return classes

    def emailEnabled(self, app):
        return self.getBatchConfigValue(app, "batch_recipients") or \
               self.getBatchConfigValue(app, "batch_use_collection") == "true"

    def getBatchConfigValue(self, app, configName, **kw):
        return app.getCompositeConfigValue(configName, self.getBatchSession(app), **kw)

    def isActionReplay(self):
        for option, _ in self.getInteractiveReplayOptions():
            if self.optionMap.has_key(option):
                return True
        return False

    def noFileAdvice(self):
        # What can we suggest if files aren't present? In this case, not much
        return ""
        
    def useVirtualDisplay(self):
        # Don't try to set it if we're using the static GUI or
        # we've requested a slow motion replay or we're trying to record a new usecase.
        return not self.isRecording() and not self.optionMap.has_key("gx") and \
               not self.isActionReplay() and not self.optionMap.has_key("coll") and not self.optionMap.runScript()
    
    def getThreadActionClasses(self):
        from actionrunner import ActionRunner
        return [ ActionRunner ]

    def getTextDisplayResponderClass(self):
        return console.TextDisplayResponder

    def isolatesDataUsingCatalogues(self, app):
        return app.getConfigValue("create_catalogues") == "true" and \
               len(app.getConfigValue("partial_copy_test_path")) > 0

    def usesCaptureMock(self, app):
        return "traffic" in app.defFileStems()
    
    def hasWritePermission(self, path):
        if os.path.isdir(path):
            return os.access(path, os.W_OK)
        else:
            return self.hasWritePermission(os.path.dirname(path))

    def getWriteDirectory(self, app):
        rootDir = self.optionMap.setPathFromOptionsOrEnv("TEXTTEST_TMP", app.getConfigValue("default_texttest_tmp")) # Location of temporary files from test runs
        if not os.path.isdir(rootDir) and not self.hasWritePermission(os.path.dirname(rootDir)):
            rootDir = self.optionMap.setPathFromOptionsOrEnv("", "$TEXTTEST_PERSONAL_CONFIG/tmp")
        return os.path.join(rootDir, self.getWriteDirectoryName(app))

    def getWriteDirectoryName(self, app):
        appDescriptor = self.getAppDescriptor()
        parts = self.getBasicRunDescriptors(app, appDescriptor) + self.getVersionDescriptors(appDescriptor) + \
                [ self.getTimeDescriptor(), str(os.getpid()) ]
        return ".".join(parts)

    def getBasicRunDescriptors(self, app, appDescriptor):
        appDescriptors = [ appDescriptor ] if appDescriptor else []
        if self.useStaticGUI(app):
            return [ "static_gui" ] + appDescriptors
        elif appDescriptors:
            return appDescriptors
        elif self.getBatchSession(app):
            return [ self.getBatchSession(app) ]
        elif self.optionMap.has_key("g"):
            return [ "dynamic_gui" ]
        else:
            return [ "console" ]

    def getTimeDescriptor(self):
        return plugins.startTimeString().replace(":", "")

    def getAppDescriptor(self):
        givenAppDescriptor = self.optionValue("a")
        if givenAppDescriptor and "," not in givenAppDescriptor:
            return givenAppDescriptor

    def getVersionDescriptors(self, appDescriptor):
        givenVersion = self.optionValue("v")
        if givenVersion:
            # Commas in path names are a bit dangerous, some applications may have arguments like
            # -path path1,path2 and just do split on the path argument.
            # We try something more obscure instead...
            versionList = plugins.commasplit(givenVersion)
            if appDescriptor:
                parts = appDescriptor.split(".", 1)
                if len(parts) > 1:
                    versionList = self.filterForApp(versionList, parts[1])
            return [ "++".join(versionList) ] if versionList else []
        else:
            return []

    def filterForApp(self, versionList, appVersionDescriptor):
        filteredVersions = []
        for version in versionList:
            if version != appVersionDescriptor:
                filteredVersions.append(version.replace(appVersionDescriptor + ".", ""))
        return filteredVersions

    def addGuiResponder(self, classes):
        from gtkgui.controller import GUIController
        classes.append(GUIController)

    def getReconnectSequence(self):
        actions = [ self.reconnectConfig.getReconnectAction() ]
        actions += [ self.getOriginalFilterer(), self.getTemporaryFilterer(), \
                     self.getTestComparator(), self.getFailureExplainer() ]
        return actions

    def getOriginalFilterer(self):
        if not self.optionMap.has_key("ignorefilters"):
            return rundependent.FilterOriginal(useFilteringStates=not self.batchMode())

    def getTemporaryFilterer(self):
        if not self.optionMap.has_key("ignorefilters"):
            return rundependent.FilterTemporary(useFilteringStates=not self.batchMode())
    
    def filterErrorText(self, app, errFile):
        filterAction = rundependent.FilterErrorText()
        return filterAction.getFilteredText(app, errFile, app)

    def applyFiltering(self, test, fileName, version):
        app = test.getAppForVersion(version)
        filterAction = rundependent.FilterAction()
        return filterAction.getFilteredText(test, fileName, app)        

    def getTestProcessor(self):        
        catalogueCreator = self.getCatalogueCreator()
        ignoreCatalogues = self.shouldIgnoreCatalogues()
        collator = self.getTestCollator()
        from traffic import SetUpCaptureMockHandlers, TerminateCaptureMockHandlers
        trafficSetup = SetUpCaptureMockHandlers(self.optionIntValue("rectraffic"))
        trafficTerminator = TerminateCaptureMockHandlers()
        return [ self.getExecHostFinder(), self.getWriteDirectoryMaker(), \
                 self.getWriteDirectoryPreparer(ignoreCatalogues), \
                 trafficSetup, catalogueCreator, collator, self.getOriginalFilterer(), self.getTestRunner(), \
                 trafficTerminator, catalogueCreator, collator, self.getTestEvaluator() ]

    def isRecording(self):
        return self.optionMap.has_key("record")
    
    def shouldIgnoreCatalogues(self):
        return self.optionMap.has_key("ignorecat") or self.isRecording()
    
    def hasPerformance(self, app, perfType=""):
        extractors = app.getConfigValue("performance_logfile_extractor")
        if (perfType and extractors.has_key(perfType)) or (not perfType and len(extractors) > 0):
            return True
        else:
            return app.hasAutomaticCputimeChecking()
    
    def hasAutomaticCputimeChecking(self, app):
        return len(app.getCompositeConfigValue("performance_test_machine", "cputime")) > 0
    
    def getFilterFileDirectories(self, apps, useOwnTmpDir):
        # 
        # - For each application, collect
        #   - temporary filter dir
        #   - all dirs in filter_file_directory
        #
        # Add these to a list. Never add the same dir twice. The first item will
        # be the default save/open dir, and the others will be added as shortcuts.
        #
        dirs = []
        for app in apps:
            writeDir = app.writeDirectory if useOwnTmpDir else None
            dirs += self._getFilterFileDirs(app, app.getDirectory(), writeDir)
        return  dirs

    def _getFilterFileDirs(self, suiteOrApp, rootDir, writeDir=None):
        dirs = []
        appDirs = suiteOrApp.getConfigValue("filter_file_directory")
        tmpDir = self.getTmpFilterDir(writeDir)
        if tmpDir and tmpDir not in dirs:
            dirs.append(tmpDir)

        for dir in appDirs:
            if os.path.isabs(dir) and os.path.isdir(dir):
                if dir not in dirs:
                    dirs.append(dir)
            else:
                newDir = os.path.join(rootDir, dir)
                if not newDir in dirs:
                    dirs.append(newDir)
        return dirs

    def getTmpFilterDir(self, writeDir):
        cmdLineDir = self.optionValue("fd")
        if cmdLineDir:
            return os.path.normpath(cmdLineDir)
        elif writeDir:
            return os.path.join(writeDir, "temporary_filter_files")
        
    def getFilterClasses(self):
        return [ TestNameFilter, plugins.TestSelectionFilter, TestRelPathFilter,
                 performance.TimeFilter, performance.FastestFilter, performance.SlowestFilter,
                 plugins.ApplicationFilter, TestDescriptionFilter ]
            
    def getAbsoluteFilterFileName(self, suite, filterFileName):
        if os.path.isabs(filterFileName):
            if os.path.isfile(filterFileName):
                return filterFileName
            else:
                raise plugins.TextTestError, "Could not find filter file at '" + filterFileName + "'"
        else:
            dirsToSearchIn = self._getFilterFileDirs(suite, suite.app.getDirectory())
            absName = suite.app.getFileName(dirsToSearchIn, filterFileName)
            if absName:
                return absName
            else:
                raise plugins.TextTestError, "No filter file named '" + filterFileName + "' found in :\n" + \
                      "\n".join(dirsToSearchIn)

    def optionListValue(self, options, key):
        if options.has_key(key):
            return plugins.commasplit(options[key])
        else:
            return []

    def findFilterFileNames(self, app, options, includeConfig):
        names = self.optionListValue(options, "f") + self.optionListValue(options, "fintersect")
        if includeConfig:
            names += app.getConfigValue("default_filter_file")
            batchSession = self.getBatchSessionForSelect(app)
            if batchSession:
                names += app.getCompositeConfigValue("batch_filter_file", batchSession)
        return names

    def findAllFilterFileNames(self, app, options, includeConfig):
        return self.findFilterFileNames(app, options, includeConfig) + \
               self.optionListValue(options, "funion") + self.optionListValue(options, "finverse")

    def getFilterList(self, app, suites, options=None, **kw):
        if options is None:
            return self.filterFileMap.setdefault(app, self._getFilterList(app, self.optionMap, suites, includeConfig=True, **kw))
        else:
            return self._getFilterList(app, options, suites, includeConfig=False, **kw)
        
    def checkFilterFileSanity(self, suite):
        # This will check all the files for existence from the input, and throw if it can't.
        # This is basically because we don't want to throw in a thread when we actually need the filters
        # if they aren't sensible for some reason
        self._checkFilterFileSanity(suite, self.optionMap, includeConfig=True)

    def _checkFilterFileSanity(self, suite, options, includeConfig=False):
        for filterFileName in self.findAllFilterFileNames(suite.app, options, includeConfig):
            optionFinder = self.makeOptionFinder(suite, filterFileName)
            self._checkFilterFileSanity(suite, optionFinder)
    
    def _getFilterList(self, app, options, suites, includeConfig, **kw):
        filters = self.getFiltersFromMap(options, app, suites, **kw)
        for filterFileName in self.findFilterFileNames(app, options, includeConfig):
            filters += self.getFiltersFromFile(app, filterFileName, suites)

        orFilterFiles = self.optionListValue(options, "funion")
        if len(orFilterFiles) > 0:
            orFilterLists = [ self.getFiltersFromFile(app, f, suites) for f in orFilterFiles ]
            filters.append(OrFilter(orFilterLists))

        notFilterFile = options.get("finverse")
        if notFilterFile:
            filters.append(NotFilter(self.getFiltersFromFile(app, notFilterFile, suites)))

        return filters

    def makeOptionFinder(self, *args):
        absName = self.getAbsoluteFilterFileName(*args)
        fileData = ",".join(plugins.readList(absName))
        return plugins.OptionFinder(fileData.split(), defaultKey="t")
        
    def getFiltersFromFile(self, app, filename, suites):
        for suite in suites:
            if suite.app is app:
                optionFinder = self.makeOptionFinder(suite, filename)
                return self._getFilterList(app, optionFinder, suites, includeConfig=False)
    
    def getFiltersFromMap(self, optionMap, app, suites, **kw):
        filters = []
        for filterClass in self.getFilterClasses():
            argument = optionMap.get(filterClass.option)
            if argument:
                filters.append(filterClass(argument, app, suites))
        batchSession = self.getBatchSessionForSelect(app)
        if batchSession:
            timeLimit = app.getCompositeConfigValue("batch_timelimit", batchSession)
            if timeLimit:
                filters.append(performance.TimeFilter(timeLimit))
        if optionMap.has_key("grep"):
            grepFile = optionMap.get("grepfile", app.getConfigValue("log_file"))
            filters.append(GrepFilter(optionMap["grep"], grepFile, **kw))
        return filters
    
    def batchMode(self):
        return self.optionMap.has_key("b")
    
    def keepTemporaryDirectories(self):
        return self.optionMap.has_key("keeptmp") or (self.batchMode() and not self.isReconnecting())

    def cleanPreviousTempDirs(self):
        return self.batchMode() and not self.isReconnecting() and not self.optionMap.has_key("keeptmp")

    def cleanWriteDirectory(self, suite):
        if not self.keepTemporaryDirectories():
            self._cleanWriteDirectory(suite)
            machine, tmpDir = self.getRemoteTmpDirectory(suite.app)
            if tmpDir:
                self.cleanRemoteDir(suite.app, machine, tmpDir)

    def cleanRemoteDir(self, app, machine, tmpDir):
        self.runCommandOn(app, machine, [ "rm", "-rf", tmpDir ])
                
    def _cleanWriteDirectory(self, suite):
        if os.path.isdir(suite.app.writeDirectory):
            plugins.rmtree(suite.app.writeDirectory)

    def makeWriteDirectory(self, app, subdir=None):
        if self.cleanPreviousTempDirs():
            self.cleanPreviousWriteDirs(app.writeDirectory)
            machine, tmpDir = self.getRemoteTmpDirectory(app)
            if tmpDir:
                # Ignore the datetime and the pid at the end
                searchParts = tmpDir.split(".")[:-2] + [ "*" ]
                fileArg = ".".join(searchParts)
                plugins.log.info("Removing previous remote write directories matching " + fileArg)
                self.runCommandOn(app, machine, [ "rm", "-rf", fileArg ])

        dirToMake = app.writeDirectory
        if subdir:
            dirToMake = os.path.join(app.writeDirectory, subdir)
        plugins.ensureDirectoryExists(dirToMake)
        app.diag.info("Made root directory at " + dirToMake)
        return dirToMake

    def cleanPreviousWriteDirs(self, writeDir):
        rootDir, basename = os.path.split(writeDir)
        if os.path.isdir(rootDir):
            # Ignore the datetime and the pid at the end
            searchParts = basename.split(".")[:-2]
            for file in os.listdir(rootDir):
                fileParts = file.split(".")
                if fileParts[:-2] == searchParts:
                    previousWriteDir = os.path.join(rootDir, file)
                    if os.path.isdir(previousWriteDir) and not plugins.samefile(previousWriteDir, writeDir):
                        plugins.log.info("Removing previous write directory " + previousWriteDir)
                        plugins.rmtree(previousWriteDir, attempts=3)
    
    def isReconnecting(self):
        return self.optionMap.has_key("reconnect")
    def getWriteDirectoryMaker(self):
        return sandbox.MakeWriteDirectory()
    def getExecHostFinder(self):
        return sandbox.FindExecutionHosts()
    def getWriteDirectoryPreparer(self, ignoreCatalogues):
        return sandbox.PrepareWriteDirectory(ignoreCatalogues)
    def getTestRunner(self):
        return RunTest()
    def getTestEvaluator(self):
        return [ self.getFileExtractor(), self.getTemporaryFilterer(), self.getTestComparator(), self.getFailureExplainer() ]
    def getFileExtractor(self):
        return [ self.getPerformanceFileMaker(), self.getPerformanceExtractor() ]
    def getCatalogueCreator(self):
        return sandbox.CreateCatalogue()
    def getTestCollator(self):
        return sandbox.CollateFiles()
    def getPerformanceExtractor(self):
        return sandbox.ExtractPerformanceFiles(self.getMachineInfoFinder())
    def getPerformanceFileMaker(self):
        return sandbox.MakePerformanceFile(self.getMachineInfoFinder())
    def getMachineInfoFinder(self):
        return sandbox.MachineInfoFinder()
    def getFailureExplainer(self):
        from knownbugs import CheckForBugs, CheckForCrashes
        return [ CheckForCrashes(), CheckForBugs() ]
    def showExecHostsInFailures(self, app):
        return self.batchMode() or app.getRunMachine() != "localhost"
    def getTestComparator(self):
        return comparetest.MakeComparisons(enableColor=self.optionMap.has_key("zen"))
    def getStateSaver(self):
        if self.batchMode():
            return batch.SaveState
        else:
            return SaveState
    def getConfigEnvironment(self, test):
        testEnvironmentCreator = self.getEnvironmentCreator(test)
        return testEnvironmentCreator.getVariables()
    def getEnvironmentCreator(self, test):
        return sandbox.TestEnvironmentCreator(test, self.optionMap)
    def getInteractiveReplayOptions(self):
        return [ ("actrep", "slow motion") ]
    def getTextResponder(self):
        return console.InteractiveResponder
    def getWebPageResponder(self):
        return batch.WebPageResponder

    # Utilities, which prove useful in many derived classes
    def optionValue(self, option):
        return self.optionMap.get(option, "")

    def optionIntValue(self, option):
        if self.optionMap.has_key(option):
            value = self.optionMap.get(option)
            return int(value) if value is not None else 1
        else:
            return 0
        
    def ignoreExecutable(self):
        return self.optionMap.has_key("s") or self.ignoreCheckout() or self.optionMap.has_key("coll") or self.optionMap.has_key("gx")

    def ignoreCheckout(self):
        return self.isReconnecting() # No use of checkouts has yet been thought up when reconnecting :)

    def setUpCheckout(self, app):
        return self.getGivenCheckoutPath(app) if not self.ignoreCheckout() else ""
    
    def verifyCheckoutValid(self, app):
        if not os.path.isabs(app.checkout):
            raise plugins.TextTestError, "could not create absolute checkout from relative path '" + app.checkout + "'"
        elif not os.path.isdir(app.checkout):
            self.handleNonExistent(app.checkout, "checkout", app)

    def checkCheckoutExists(self, app):
        if not app.checkout:
            return "" # Allow empty checkout, means no checkout is set, basically
        
        try: 
            self.verifyCheckoutValid(app)
        except plugins.TextTestError, e:
            if self.ignoreExecutable():
                plugins.printWarning(str(e), stdout=True)
                return ""
            else:
                raise

    def checkSanity(self, suite):
        if not self.ignoreCheckout():
            self.checkCheckoutExists(suite.app)
        if not self.ignoreExecutable():
            self.checkExecutableExists(suite)

        self.checkFilterFileSanity(suite)
        self.checkCaptureMockMigration(suite)
        self.checkConfigSanity(suite.app)
        batchSession = self.getBatchSessionForSelect(suite.app)
        if batchSession is not None and not self.optionMap.has_key("coll"):
            batchFilter = batch.BatchVersionFilter(batchSession)
            batchFilter.verifyVersions(suite.app)
        if self.isReconnecting():
            self.reconnectConfig.checkSanity(suite.app)
        # side effects really from here on :(
        if self.readsTestStateFiles():
            # Reading stuff from stored pickle files, need to set up categories independently
            self.setUpPerformanceCategories(suite.app)

    def checkCaptureMockMigration(self, suite):
        if (suite.getCompositeConfigValue("collect_traffic", "asynchronous") or \
            suite.getConfigValue("collect_traffic_python")) and \
               not self.optionMap.runScript():
            raise plugins.TextTestError, "collect_traffic settings have been deprecated.\n" + \
                  "They have been replaced by using the CaptureMock program which is now separate from TextTest.\n" + \
                  "Please run with '-s traffic.ConvertToCaptureMock' and consult the migration notes at\n" + \
                  os.path.join(plugins.installationDir("doc"), "MigrationNotes_from_3.20") + "\n"

    def readsTestStateFiles(self):
        return self.isReconnecting() or self.optionMap.has_key("coll")

    def setUpPerformanceCategories(self, app):
        # We don't create these in the normal way, so we don't know what they are.
        allCategories = app.getConfigValue("performance_descriptor_decrease").values() + \
                        app.getConfigValue("performance_descriptor_increase").values()
        for cat in allCategories:
            if cat:
                plugins.addCategory(*plugins.commasplit(cat))
                
    def checkExecutableExists(self, suite):
        executable = suite.getConfigValue("executable")
        if self.executableShouldBeFile(suite.app, executable) and not os.path.isfile(executable):
            self.handleNonExistent(executable, "executable program", suite.app)

        interpreterStr = suite.getConfigValue("interpreter")
        if interpreterStr:
            interpreter = plugins.splitcmd(interpreterStr)[0]
            if os.path.isabs(interpreter) and not os.path.exists(interpreter):
                self.handleNonExistent(interpreter, "interpreter program", suite.app)

    def pathExistsRemotely(self, app, path, machine):
        exitCode = self.runCommandOn(app, machine, [ "test", "-e", path ], collectExitCode=True)
        return exitCode == 0

    def checkConnection(self, app, machine):
        self.runCommandAndCheckMachine(app, machine, [ "echo", "hello" ])
 
    def handleNonExistent(self, path, desc, app):
        message = "The " + desc + " '" + path + "' does not exist"
        remoteCopy = app.getConfigValue("remote_copy_program")
        if remoteCopy:
            runMachine = app.getRunMachine()
            if runMachine != "localhost":
                if not self.pathExistsRemotely(app, path, runMachine):
                    self.checkConnection(app, runMachine) # throws if we can't get to it
                    raise plugins.TextTestError, message + ", either locally or on machine '" + runMachine + "'."
        else:
            raise plugins.TextTestError, message + "."

    def getRemoteTmpDirectory(self, app):
        remoteCopy = app.getConfigValue("remote_copy_program")
        if remoteCopy:
            runMachine = app.getRunMachine()
            if runMachine != "localhost":
                return runMachine, "${HOME}/.texttest/tmp/" + os.path.basename(app.writeDirectory)
        return "localhost", None

    def getRemoteTestTmpDir(self, test):
        machine, appTmpDir = self.getRemoteTmpDirectory(test.app)
        if appTmpDir:
            return machine, os.path.join(appTmpDir, test.app.name + test.app.versionSuffix(), test.getRelPath())
        else:
            return machine, appTmpDir

    def hasChanged(self, var, value):
        return os.getenv(var) != value
                
    def executableShouldBeFile(self, app, executable):
        if os.path.isabs(executable):
            return True

        # If it's part of the data it will be available as a relative path anyway
        if executable in app.getDataFileNames():
            return False
        
        # For finding java classes, don't warn if they don't exist as files...
        interpreter = app.getConfigValue("interpreter")
        return ("java" not in interpreter and "jython" not in interpreter) or executable.endswith(".jar")
    
    def checkConfigSanity(self, app):
        for key in app.getConfigValue("collate_file"):
            if "." in key or "/" in key:
                raise plugins.TextTestError, "Cannot collate files to stem '" + key + "' - '.' and '/' characters are not allowed"

        definitionFileStems = app.defFileStems()
        definitionFileStems += [ stem + "." + app.name for stem in definitionFileStems ]
        for dataFileName in app.getDataFileNames():
            if dataFileName in definitionFileStems:
                raise plugins.TextTestError, "Cannot name data files '" + dataFileName + \
                      "' - this name is reserved by TextTest for a particular kind of definition file.\n" + \
                      "Please adjust the naming in your config file."

    def getGivenCheckoutPath(self, app):
        if self.optionMap.has_key("c"):
            extraVersions, extraCheckouts = self.getCheckoutExtraVersions(app)
            for versionName, checkout in zip(extraVersions, extraCheckouts):
                if versionName in app.versions:
                    return checkout

        checkout = self.getCheckout(app)
        return self.expandCheckout(checkout, app)

    def expandCheckout(self, checkout, app):
        if os.path.isabs(checkout):
            return os.path.normpath(checkout)
        checkoutLocations = app.getCompositeConfigValue("checkout_location", checkout, expandVars=False)
        if len(checkoutLocations) > 0:
            return self.makeAbsoluteCheckout(checkoutLocations, checkout, app)
        else:
            return checkout

    def getCheckout(self, app):
        if self.optionMap.has_key("c"):
            return plugins.commasplit(self.optionMap["c"])[0]

        # Under some circumstances infer checkout from batch session
        batchSession = self.getBatchSession(app)
        if batchSession and  batchSession != "default" and \
               app.getConfigValue("checkout_location").has_key(batchSession):
            return batchSession
        else:
            return app.getConfigValue("default_checkout")        

    def makeAbsoluteCheckout(self, locations, checkout, app):
        isSpecific = app.getConfigValue("checkout_location").has_key(checkout)
        for location in locations:
            fullCheckout = self.absCheckout(location, checkout, isSpecific)
            if os.path.isdir(fullCheckout):
                return fullCheckout
        return self.absCheckout(locations[0], checkout, isSpecific)

    def absCheckout(self, location, checkout, isSpecific):
        locationWithName = Template(location).safe_substitute(TEXTTEST_CHECKOUT_NAME=checkout)
        fullLocation = os.path.normpath(os.path.expanduser(os.path.expandvars(locationWithName)))
        if isSpecific or "TEXTTEST_CHECKOUT_NAME" in location:
            return fullLocation
        else:
            # old-style: infer expansion in default checkout
            return os.path.join(fullLocation, checkout)

    def recomputeProgress(self, test, state, observers):
        if state.isComplete():
            if state.hasResults():
                state.recalculateStdFiles(test)
                fileFilter = rundependent.FilterResultRecompute()
                fileFilter(test)
                state.recalculateComparisons(test)
                newState = state.makeNewState(test, "recalculated")
                test.changeState(newState)
        else:
            collator = test.app.getTestCollator()
            collator.tryFetchRemoteFiles(test)
            fileFilter = rundependent.FilterProgressRecompute()
            fileFilter(test)
            comparator = self.getTestComparator()
            comparator.recomputeProgress(test, state, observers)

    def getRunDescription(self, test):
        return RunTest().getRunDescription(test)

    # For display in the GUI
    def extraReadFiles(self, testArg):
        return {}
    def printHelpScripts(self):
        pass
    def printHelpDescription(self):
        print "The " + self.__class__.__module__ + " configuration is a published configuration. Consult the online documentation."
    def printHelpOptions(self):
        pass
    def printHelpText(self):
        self.printHelpDescription()
        print "\nAdditional Command line options supported :"
        print "-------------------------------------------"
        self.printHelpOptions()
        print "\nPython scripts: (as given to -s <module>.<class> [args])"
        print "--------------------------------------------------------"
        self.printHelpScripts()
    def getDefaultMailAddress(self):
        user = os.getenv("USER", "$USER")
        return user + "@localhost"
    def getDefaultTestOverviewColours(self):
        colours = {}
        for wkday in plugins.weekdays:
            colours["run_" + wkday + "_fg"] = "black"
        colours["column_header_bg"] = "gray1"
        colours["row_header_bg"] = "#FFFFCC"
        colours["performance_fg"] = "red6"
        colours["memory_bg"] = "pink"
        colours["success_bg"] = "#CEEFBD"
        colours["failure_bg"] = "#FF3118"
        colours["knownbug_bg"] = "#FF9900"
        colours["incomplete_bg"] = "#8B1A1A"
        colours["no_results_bg"] = "gray2"
        colours["performance_bg"] = "#FFC6A5"
        colours["test_default_fg"] = "black"
        return colours

    def getDefaultPageName(self, app):
        pageName = app.fullName()
        fullVersion = app.getFullVersion()
        if fullVersion:
            pageName += " - version " + fullVersion
        return pageName
    def getDefaultCollectCompulsoryVersions(self):
        return { "default" : [] }
    def setBatchDefaults(self, app):
        # Batch values. Maps from session name to values
        app.setConfigDefault("smtp_server", "localhost", "Server to use for sending mail in batch mode")
        app.setConfigDefault("smtp_server_username", "", "Username for SMTP authentication when sending mail in batch mode")
        app.setConfigDefault("smtp_server_password", "", "Password for SMTP authentication when sending mail in batch mode")
        app.setConfigDefault("batch_result_repository", { "default" : "" }, "Directory to store historical batch results under")
        app.setConfigDefault("historical_report_location", { "default" : "" }, "Directory to create reports on historical batch data under")
        app.setConfigDefault("historical_report_page_name", { "default" : self.getDefaultPageName(app) }, "Header for page on which this application should appear")
        app.setConfigDefault("historical_report_colours", self.getDefaultTestOverviewColours(), "Colours to use for historical batch HTML reports")
        app.setConfigDefault("historical_report_subpages", { "default" : [ "Last six runs" ]}, "Names of subselection pages to generate as part of historical report")
        app.setConfigDefault("historical_report_subpage_cutoff", { "default" : 100000, "Last six runs" : 6 }, "How many runs should the subpage show, starting from the most recent?")
        app.setConfigDefault("historical_report_subpage_weekdays", { "default" : [] }, "Which weekdays should the subpage apply to (empty implies all)?")
        app.setConfigDefault("historical_report_resource_pages", { "default": [ "" ] }, "Which performance/memory pages should be generated by default on running -coll")
        app.setConfigDefault("historical_report_resource_page_tables", { "default": []}, "Resource names to generate the tables for the relevant performance/memory pages")
        app.setConfigDefault("historical_report_piechart_summary", { "default": "false" }, "Generate pie chart summary page rather than default HTML tables.")
        app.setConfigDefault("batch_sender", { "default" : self.getDefaultMailAddress() }, "Sender address to use sending mail in batch mode")
        app.setConfigDefault("batch_recipients", { "default" : "" }, "Comma-separated addresses to send mail to in batch mode")
        app.setConfigDefault("batch_timelimit", { "default" : "" }, "Maximum length of test to include in batch mode runs")
        app.setConfigDefault("batch_filter_file", { "default" : [] }, "Generic filter for batch session, more flexible than timelimit")
        app.setConfigDefault("batch_use_collection", { "default" : "false" }, "Do we collect multiple mails into one in batch mode")
        app.setConfigDefault("batch_junit_format", { "default" : "false" }, "Do we write out results in junit format in batch mode")
        app.setConfigDefault("batch_junit_folder", { "default" : "" }, "Which folder to write test results in junit format in batch mode. Only useful together with batch_junit_format")
        app.setConfigDefault("batch_collect_max_age_days", { "default" : 100000 }, "When collecting multiple messages, what is the maximum age of run that we should accept?")
        app.setConfigDefault("batch_collect_compulsory_version", self.getDefaultCollectCompulsoryVersions(), "When collecting multiple messages, which versions should be expected and give an error if not present?")
        app.setConfigDefault("batch_mail_on_failure_only", { "default" : "false" }, "Send mails only if at least one test fails")
        app.setConfigDefault("batch_use_version_filtering", { "default" : "false" }, "Which batch sessions use the version filtering mechanism")
        app.setConfigDefault("batch_version", { "default" : [] }, "List of versions to allow if batch_use_version_filtering enabled")
        app.setConfigAlias("testoverview_colours", "historical_report_colours")
        
    def setPerformanceDefaults(self, app):
        # Performance values
        app.setConfigDefault("cputime_include_system_time", 0, "Include system time when measuring CPU time?")
        app.setConfigDefault("performance_logfile", { "default" : [] }, "Which result file to collect performance data from")
        app.setConfigDefault("performance_logfile_extractor", {}, "What string to look for when collecting performance data")
        app.setConfigDefault("performance_test_machine", { "default" : [], "*mem*" : [ "any" ] }, \
                             "List of machines where performance can be collected")
        app.setConfigDefault("performance_variation_%", { "default" : 10.0 }, "How much variation in performance is allowed")
        app.setConfigDefault("performance_variation_serious_%", { "default" : 0.0 }, "Additional cutoff to performance_variation_% for extra highlighting")                
        app.setConfigDefault("use_normalised_percentage_change", { "default" : "true" }, \
                             "Do we interpret performance percentage changes as normalised (symmetric) values?")
        app.setConfigDefault("performance_test_minimum", { "default" : 0.0 }, \
                             "Minimum time/memory to be consumed before data is collected")
        app.setConfigDefault("performance_descriptor_decrease", self.defaultPerfDecreaseDescriptors(), "Descriptions to be used when the numbers decrease in a performance file")
        app.setConfigDefault("performance_descriptor_increase", self.defaultPerfIncreaseDescriptors(), "Descriptions to be used when the numbers increase in a performance file")
        app.setConfigDefault("performance_unit", self.defaultPerfUnits(), "Name to be used to identify the units in a performance file")
        app.setConfigDefault("performance_ignore_improvements", { "default" : "false" }, "Should we ignore all improvements in performance?")
        app.setConfigAlias("performance_use_normalised_%", "use_normalised_percentage_change")
        
    def setUsecaseDefaults(self, app):
        app.setConfigDefault("use_case_record_mode", "disabled", "Mode for Use-case recording (GUI, console or disabled)")
        app.setConfigDefault("use_case_recorder", "", "Which Use-case recorder is being used")
        app.setConfigDefault("slow_motion_replay_speed", 3.0, "How long in seconds to wait between each GUI action")
        app.setConfigDefault("virtual_display_machine", [ "localhost" ], \
                             "(UNIX) List of machines to run virtual display server (Xvfb) on")
        app.setConfigDefault("virtual_display_extra_args", "", \
                             "(UNIX) Extra arguments (e.g. bitdepth) to supply to virtual display server (Xvfb)")
        app.setConfigDefault("virtual_display_hide_windows", "true", "(Windows) Whether to emulate the virtual display handling on Windows by hiding the SUT's windows")

    def defaultPerfUnits(self):
        units = {}
        units["default"] = "seconds"
        units["*mem*"] = "MB"
        return units

    def defaultPerfDecreaseDescriptors(self):
        descriptors = {}
        descriptors["default"] = ""
        descriptors["memory"] = "smaller, memory-, used less memory"
        descriptors["cputime"] = "faster, faster, ran faster"
        return descriptors

    def defaultPerfIncreaseDescriptors(self):
        descriptors = {}
        descriptors["default"] = ""
        descriptors["memory"] = "larger, memory+, used more memory"
        descriptors["cputime"] = "slower, slower, ran slower"
        return descriptors

    def defaultSeverities(self):
        severities = {}
        severities["errors"] = 1
        severities["output"] = 1
        severities["stderr"] = 1
        severities["stdout"] = 1
        severities["usecase"] = 1
        severities["performance"] = 2
        severities["catalogue"] = 2
        severities["default"] = 99
        return severities

    def defaultDisplayPriorities(self):
        prios = {}
        prios["default"] = 99
        return prios

    def getDefaultCollations(self):
        if os.name == "posix":
            return { "stacktrace" : [ "core*" ] }
        else:
            return { "" : [] }

    def getDefaultCollateScripts(self):
        if os.name == "posix":
            return { "default" : [], "stacktrace" : [ "interpretcore.py" ] }
        else:
            return { "default" : [] }

    def getStdoutName(self, namingScheme):
        if namingScheme == "classic":
            return "output"
        else:
            return "stdout"

    def getStderrName(self, namingScheme):
        if namingScheme == "classic":
            return "errors"
        else:
            return "stderr"

    def getStdinName(self, namingScheme):
        if namingScheme == "classic":
            return "input"
        else:
            return "stdin"

    def setComparisonDefaults(self, app, homeOS, namingScheme):
        app.setConfigDefault("log_file", self.getStdoutName(namingScheme), "Result file to search, by default")
        app.setConfigDefault("failure_severity", self.defaultSeverities(), \
                             "Mapping of result files to how serious diffs in them are")
        app.setConfigDefault("failure_display_priority", self.defaultDisplayPriorities(), \
                             "Mapping of result files to which order they should be shown in the text info window.")
        app.setConfigDefault("floating_point_tolerance", { "default" : 0.0 }, "Which tolerance to apply when comparing floating point values in output")
        app.setConfigDefault("relative_float_tolerance", { "default" : 0.0 }, "Which relative tolerance to apply when comparing floating point values")

        app.setConfigDefault("collate_file", self.getDefaultCollations(), "Mapping of result file names to paths to collect them from")
        app.setConfigDefault("collate_script", self.getDefaultCollateScripts(), "Mapping of result file names to scripts which turn them into suitable text")
        trafficText = "Deprecated. Use CaptureMock."
        app.setConfigDefault("collect_traffic", { "default": [], "asynchronous": [] }, trafficText)
        app.setConfigDefault("collect_traffic_environment", { "default" : [] }, trafficText)
        app.setConfigDefault("collect_traffic_python", [], trafficText)
        app.setConfigDefault("collect_traffic_python_ignore_callers", [], trafficText)
        app.setConfigDefault("collect_traffic_use_threads", "true", trafficText)
        app.setConfigDefault("collect_traffic_client_server", "false", trafficText)
        app.setConfigDefault("run_dependent_text", { "default" : [] }, "Mapping of patterns to remove from result files")
        app.setConfigDefault("unordered_text", { "default" : [] }, "Mapping of patterns to extract and sort from result files")
        app.setConfigDefault("create_catalogues", "false", "Do we create a listing of files created/removed by tests")
        app.setConfigDefault("catalogue_process_string", "", "String for catalogue functionality to identify processes created")
        app.setConfigDefault("binary_file", [], "Which output files are known to be binary, and hence should not be shown/diffed?")
        
        app.setConfigDefault("discard_file", [], "List of generated result files which should not be compared")
        rectrafficValue = self.optionIntValue("rectraffic")
        if rectrafficValue == 1:
            # Re-record everything. Don't use this when only recording additional new stuff
            # Should possibly have some way to configure this
            app.addConfigEntry("implied", "rectraffic", "base_version")
        if self.isRecording():
            app.addConfigEntry("implied", "recusecase", "base_version")
        if homeOS != "any" and homeOS != os.name:
            app.addConfigEntry("implied", os.name, "base_version")
        app.setConfigAlias("collect_traffic_py_module", "collect_traffic_python")
        
    def defaultViewProgram(self, homeOS):
        if os.name == "posix":
            return "emacs"
        else:
            if homeOS == "posix":
                # Notepad cannot handle UNIX line-endings: for cross platform suites use wordpad by default...
                return "wordpad"
            else:
                return "notepad"
    def defaultFollowProgram(self):
        if os.name == "posix":
            return "xterm -bg white -T $TEXTTEST_FOLLOW_FILE_TITLE -e tail -f"
        else:
            return "baretail"
        
    def setExternalToolDefaults(self, app, homeOS):
        app.setConfigDefault("text_diff_program", "diff", \
                             "External program to use for textual comparison of files")
        app.setConfigDefault("lines_of_text_difference", 30, "How many lines to present in textual previews of file diffs")
        app.setConfigDefault("max_width_text_difference", 500, "How wide lines can be in textual previews of file diffs")
        app.setConfigDefault("max_file_size", { "default": "-1" }, "The maximum file size to load into external programs, in bytes. -1 means no limit.")
        app.setConfigDefault("text_diff_program_filters", { "default" : [], "diff" : [ "^<", "^>" ]}, "Filters that should be applied for particular diff tools to aid with grouping in dynamic GUI")
        app.setConfigDefault("diff_program", { "default": "tkdiff" }, "External program to use for graphical file comparison")
        app.setConfigDefault("view_program", { "default": self.defaultViewProgram(homeOS) },  \
                              "External program(s) to use for viewing and editing text files")
        app.setConfigDefault("view_file_on_remote_machine", { "default" : 0 }, "Do we try to start viewing programs on the test execution machine?")
        app.setConfigDefault("follow_program", { "default": self.defaultFollowProgram() }, "External program to use for following progress of a file")
        app.setConfigDefault("follow_file_by_default", 0, "When double-clicking running files, should we follow progress or just view them?")
        app.setConfigDefault("bug_system_location", {}, "The location of the bug system we wish to extract failure information from.")
        app.setConfigDefault("bug_system_username", {}, "Username to use when logging in to bug systems defined in bug_system_location")
        app.setConfigDefault("bug_system_password", {}, "Password to use when logging in to bug systems defined in bug_system_location")
        app.setConfigAlias("text_diff_program_max_file_size", "max_file_size")
        
    def setInterfaceDefaults(self, app):
        app.setConfigDefault("default_interface", "static_gui", "Which interface to start if none of -con, -g and -gx are provided")
        # These configure the GUI but tend to have sensible defaults per application
        app.setConfigDefault("gui_entry_overrides", { "default" : "<not set>" }, "Default settings for entries in the GUI")
        app.setConfigDefault("gui_entry_options", { "default" : [] }, "Default drop-down box options for GUI entries")
        app.setConfigDefault("suppress_stderr_text", [], "List of patterns which, if written on TextTest's own stderr, should not be propagated to popups and further logfiles")
        app.setConfigAlias("suppress_stderr_popup", "suppress_stderr_text")
        
    def getDefaultRemoteProgramOptions(self):
        # The aim is to ensure they never hang, but always return errors if contact not possible
        # Disable passwords: only use public key based authentication.
        # Also disable hostkey checking, we assume we don't run tests on untrusted hosts.
        # Also don't run tests on machines which take a very long time to connect to...
        sshOptions = "-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10"
        return { "default": "", "ssh" : sshOptions,
                 "rsync" : "-azLp", "scp": "-Crp " + sshOptions }

    def getCommandArgsOn(self, app, machine, cmdArgs, graphical=False):
        if machine == "localhost":
            return cmdArgs
        else:
            args = self.getRemoteProgramArgs(app, "remote_shell_program")
            if graphical and args[0] == "ssh":
                args.append("-Y")
            args.append(machine)
            if graphical and args[0] == "rsh":
                args += [ "env", "DISPLAY=" + self.getFullDisplay() ]
            args += cmdArgs
            if graphical:
                remoteTmp = app.getRemoteTmpDirectory()[1]
                if remoteTmp:
                    args[-1] = args[-1].replace(app.writeDirectory, remoteTmp)
                for i in range(len(args)):
                    # Remote shells cause spaces etc to be interpreted several times
                    args[i] = args[i].replace(" ", "\ ")
            return args

    def getFullDisplay(self):
        display = os.getenv("DISPLAY", "")
        hostaddr = plugins.gethostname()
        if display.startswith(":"):
            return hostaddr + display
        else:
            return display.replace("localhost", hostaddr)

    def runCommandOn(self, app, machine, cmdArgs, collectExitCode=False):
        allArgs = self.getCommandArgsOn(app, machine, cmdArgs)
        if allArgs[0] == "rsh" and collectExitCode:
            searchStr = "remote cmd succeeded"
            # Funny tricks here because rsh does not forward the exit status of the program it runs
            allArgs += [ "&&", "echo", searchStr ]
            diag = logging.getLogger("remote commands")
            proc = subprocess.Popen(allArgs, stdin=open(os.devnull), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output = proc.communicate()[0]
            diag.info("Running remote command " + repr(allArgs) + ", output was:\n" + output)
            return searchStr not in output # Return an "exit code" which is 0 when we succeed!
        else:
            return subprocess.call(allArgs, stdin=open(os.devnull), stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT)

    def runCommandAndCheckMachine(self, app, machine, cmdArgs):
        allArgs = self.getCommandArgsOn(app, machine, cmdArgs)
        proc = subprocess.Popen(allArgs, stdin=open(os.devnull), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = proc.communicate()[0]
        exitCode = proc.returncode
        if exitCode > 0:
            raise plugins.TextTestError, "Unable to contact machine '" + machine + \
                  "'.\nMake sure you have passwordless access set up correctly. The failing command was:\n" + \
                  " ".join(allArgs) + "\n\nThe command produced the following output:\n" + output.strip()

    def ensureRemoteDirExists(self, app, machine, dirname):
        self.runCommandAndCheckMachine(app, machine, [ "mkdir", "-p", plugins.quote(dirname) ])

    @staticmethod
    def getRemotePath(fileName, machine):
        if machine == "localhost":
            # Right now the only way we can run remote execution on a Windows system is using Cygwin
            # Remote copy programs like 'scp' assume that colons separate hostnames and so don't work
            # on classic Windows paths.
            # Assume for now that we can convert it to a Cygwin path.
            drive, tail = os.path.splitdrive(fileName)
            if drive:
                cygwinDrive = '/cygdrive/' + drive[0].lower()
                return cygwinDrive + tail
            else:
                return fileName
        else:
            return machine + ":" + plugins.quote(fileName)
                                                 
    def copyFileRemotely(self, app, srcFile, srcMachine, dstFile, dstMachine):
        srcPath = self.getRemotePath(srcFile, srcMachine)
        dstPath = self.getRemotePath(dstFile, dstMachine)
        args = self.getRemoteProgramArgs(app, "remote_copy_program") + [ srcPath, dstPath ]
        return subprocess.call(args, stdin=open(os.devnull), stdout=open(os.devnull, "w")) #, stderr=subprocess.STDOUT)

    def getRemoteProgramArgs(self, app, setting):
        progStr = app.getConfigValue(setting)
        progArgs = plugins.splitcmd(progStr)
        argStr = app.getCompositeConfigValue("remote_program_options", progArgs[0])
        return progArgs + plugins.splitcmd(argStr)

    def setMiscDefaults(self, app, namingScheme):
        app.setConfigDefault("default_texttest_tmp", "$TEXTTEST_PERSONAL_CONFIG/tmp", "Default value for $TEXTTEST_TMP, if it is not set")
        app.setConfigDefault("checkout_location", { "default" : []}, "Absolute paths to look for checkouts under")
        app.setConfigDefault("default_checkout", "", "Default checkout, relative to the checkout location")
        app.setConfigDefault("remote_shell_program", "rsh", "Program to use for running commands remotely")
        app.setConfigDefault("remote_program_options", self.getDefaultRemoteProgramOptions(), "Default options to use for particular remote shell programs")
        app.setConfigDefault("remote_copy_program", "", "(UNIX) Program to use for copying files remotely, in case of non-shared file systems")
        app.setConfigDefault("default_filter_file", [], "Filter file to use by default, generally only useful for versions")
        app.setConfigDefault("test_data_environment", {}, "Environment variables to be redirected for linked/copied test data")
        app.setConfigDefault("filter_file_directory", [ "filter_files" ], "Default directories for test filter files, relative to an application directory.")
        app.setConfigDefault("extra_version", [], "Versions to be run in addition to the one specified")
        app.setConfigDefault("batch_extra_version", { "default" : [] }, "Versions to be run in addition to the one specified, for particular batch sessions")
        app.setConfigDefault("save_filtered_file_stems", [], "Files where the filtered version should be saved rather than the SUT output")
        # Applies to any interface...
        app.setConfigDefault("auto_sort_test_suites", 0, "Automatically sort test suites in alphabetical order. 1 means sort in ascending order, -1 means sort in descending order.")
        app.addConfigEntry("builtin", "options", "definition_file_stems")
        app.addConfigEntry("builtin", "interpreter_options", "definition_file_stems")
        app.addConfigEntry("regenerate", "usecase", "definition_file_stems")
        app.addConfigEntry("builtin", self.getStdinName(namingScheme), "definition_file_stems")
        app.addConfigEntry("builtin", "knownbugs", "definition_file_stems")
        app.setConfigAlias("test_list_files_directory", "filter_file_directory")
        
    def setApplicationDefaults(self, app):
        homeOS = app.getConfigValue("home_operating_system")
        namingScheme = app.getConfigValue("filename_convention_scheme")
        self.setComparisonDefaults(app, homeOS, namingScheme)
        self.setExternalToolDefaults(app, homeOS)
        self.setInterfaceDefaults(app)
        self.setMiscDefaults(app, namingScheme)
        self.setBatchDefaults(app)
        self.setPerformanceDefaults(app)
        self.setUsecaseDefaults(app)

    def setDependentConfigDefaults(self, app):
        # For setting up configuration where the config file needs to have been read first
        # Should return True if it does anything that could cause new config files to be found
        interpreter = app.getConfigValue("interpreter")
        if "python" in interpreter or "storytext" in interpreter:
            app.addConfigEntry("default", "testcustomize.py", "definition_file_stems")
        return False


class SaveState(plugins.Responder):
    def notifyComplete(self, test):
        if test.state.isComplete(): # might look weird but this notification also comes in scripts etc.
            test.saveState()


class OrFilter(plugins.Filter):
    def __init__(self, filterLists):
        self.filterLists = filterLists
    def accepts(self, test):
        return reduce(operator.or_, (test.isAcceptedByAll(filters, checkContents=False) for filters in self.filterLists), False)
    def acceptsTestCase(self, test):
        return self.accepts(test)
    def acceptsTestSuite(self, suite):
        return self.accepts(suite)
    def acceptsTestSuiteContents(self, suite):
        return reduce(operator.or_, (self.contentsAccepted(suite, filters) for filters in self.filterLists), False)
    def contentsAccepted(self, suite, filters):
        return reduce(operator.and_, (filter.acceptsTestSuiteContents(suite) for filter in filters), True)

class NotFilter(plugins.Filter):
    def __init__(self, filters):
        self.filters = filters
    def acceptsTestCase(self, test):
        return not test.isAcceptedByAll(self.filters)
    
class TestNameFilter(plugins.TextFilter):
    option = "t"
    def acceptsTestCase(self, test):
        return self.stringContainsText(test.name)

class TestRelPathFilter(plugins.TextFilter):
    option = "ts"
    def parseInput(self, filterText, *args):
        # Handle paths pasted from web page
        return [ text.replace(" ", "/") for text in plugins.commasplit(filterText) ]

    def acceptsTestCase(self, test):
        return self.stringContainsText(test.getRelPath())


class GrepFilter(plugins.TextFilter):
    def __init__(self, filterText, fileStem, useTmpFiles=False):
        plugins.TextFilter.__init__(self, filterText)
        self.fileStem = fileStem
        self.useTmpFiles = useTmpFiles
        
    def acceptsTestCase(self, test):
        if self.fileStem == "free_text":
            return self.stringContainsText(test.state.freeText)
        for logFile in self.findAllFiles(test):
            if self.matches(logFile):
                return True
        return False

    def findAllFiles(self, test):
        if self.useTmpFiles:
            files = []
            try:
                for comparison in test.state.allResults:
                    if comparison.tmpFile and fnmatch(comparison.stem, self.fileStem) and os.path.isfile(comparison.tmpFile):
                        files.append(comparison.tmpFile)
                return files
            except AttributeError:
                return []
        else:
            return self.findAllStdFiles(test)

    def findAllStdFiles(self, test):
        logFiles = []
        for fileName in test.getFileNamesMatching(self.fileStem):
            if os.path.isfile(fileName):
                logFiles.append(fileName)
            else:
                test.refreshFiles()
                return self.findAllStdFiles(test)
        return logFiles

    def matches(self, logFile):
        for line in open(logFile).xreadlines():
            if self.stringContainsText(line):
                return True
        return False


class TestDescriptionFilter(plugins.TextFilter):
    option = "desc"
    def acceptsTestCase(self, test):
        return self.stringContainsText(test.description)

