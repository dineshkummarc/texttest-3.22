
import sys, os, logging.config, string, shutil, socket, time, re, stat, subprocess, shlex, types, fnmatch
from ordereddict import OrderedDict
from traceback import format_exception
from threading import currentThread
from Queue import Queue, Empty
from glob import glob
from copy import deepcopy
from datetime import datetime

# We standardise around UNIX paths, it's all much easier that way. They work fine,
# and they don't run into weird issues in being confused with escape characters

# basically posixpath.join, adapted to be portable...
def joinpath(a, *p):
    path = a
    for b in p:
        if os.path.isabs(b) and (path[1:2] != ":" or b[1:2] == ":"):
            path = b
        elif path == '' or path.endswith('/'):
            path +=  b
        else:
            path += '/' + b
    return path

os.path.join = joinpath
if os.name == "nt":
    import posixpath
    os.sep = posixpath.sep
    os.path.sep = posixpath.sep
    os.path.normpath = posixpath.normpath
    orig_abspath = os.path.abspath
    def abspath(f):
        return orig_abspath(f).replace("\\", "/")
    os.path.abspath = abspath
    os.path.realpath = abspath
        
    
class Callable:
    def __init__(self, method, *args):
        self.method = method
        self.extraArgs = args
    def __call__(self, *calledArgs, **kw):
        toUse = calledArgs + self.extraArgs
        return self.method(*toUse, **kw)
    def __eq__(self, other):
        return isinstance(other, Callable) and self.method == other.method and self.extraArgs == other.extraArgs
    def __hash__(self):
        return hash((self.method, self.extraArgs))
    def __deepcopy__(self, memo):
        return self # don't copy these

def findInstallationRoots():
    installationRoot = os.path.dirname(os.path.dirname(__file__)).replace("\\", "/")
    if os.path.basename(installationRoot) == "generic":
        siteRoot = os.path.dirname(installationRoot)
        return [ installationRoot, siteRoot ]
    else:
        siteDir = os.path.join(installationRoot, "site")
        if os.path.isdir(siteDir):
            return [ installationRoot, siteDir ]
        else:
            return [ installationRoot ]

globalStartTime = datetime.now()
datetimeFormat = "%d%b%H:%M:%S"
installationRoots = findInstallationRoots()
# Don't read these from Python as the names depend on the locale!
weekdays = [ "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday" ]
# A few version control systems we might run into... list lifted from emacs "grep-find-ignored-directories"
# and removed the ones I'd never heard of...
controlDirNames = [ "CVS", ".svn", ".bzr", ".hg", ".git", "RCS", "_darcs", "{arch}" ]

# Useful utility...
def localtime(format=datetimeFormat):
    return datetime.now().strftime(format)

def startTimeString():
    return globalStartTime.strftime(datetimeFormat)

def importAndCall(moduleName, callableName, *args):
    command = "from " + moduleName + " import " + callableName + " as _callable"
    exec command
    return _callable(*args)

def installationDir(name):
    # Generic modules only, we're confident we know where they are
    return os.path.join(installationRoots[0], name)

def getTextTestProgram():
    slaveCmd = os.getenv("TEXTTEST_SLAVE_CMD", sys.argv[0]) # TextTest start-script for starting subsequent processes
    if not slaveCmd:
        # To allow it to be reset, the above form is for documentation...
        slaveCmd = sys.argv[0]
    return slaveCmd

def installationPath(*pathElems):
    for instRoot in installationRoots:
        instPath = os.path.join(instRoot, *pathElems)
        if os.path.exists(instPath):
            return instPath

def getPersonalDir(dataDirName):
    envVar = "TEXTTEST_PERSONAL_" + dataDirName.upper()
    return os.getenv(envVar, os.path.join(getPersonalConfigDir(), dataDirName))

def quote(value):
    quoteChar = "'"
    if quoteChar in value:
        return value # don't double-quote
    # Make sure the home directory gets expanded...
    quotedValue = quoteChar + value + quoteChar
    quotedValue = quotedValue.replace("${", quoteChar + "${")
    quotedValue = quotedValue.replace("}", "}" + quoteChar)
    if quotedValue.startswith(quoteChar * 2):
        quotedValue = quotedValue[2:]
    if quotedValue.endswith(quoteChar * 2):
        quotedValue = quotedValue[:-2]
    return quotedValue


def pluralise(num, name):
    if num == 1:
        return "1 " + name
    else:
        return str(num) + " " + name + "s"


def findDataDirs(includeSite=True, includePersonal=False, dataDirName="etc"):
    if includeSite:
        dirs = [ os.path.join(instRoot, dataDirName) for instRoot in installationRoots ]
    else:
        dirs = [ os.path.join(installationRoots[0], dataDirName) ]
    if includePersonal:
        dirs.append(getPersonalDir(dataDirName))
    return dirs

def findDataPaths(filePatterns, *args, **kwargs):
    paths = []
    for dir in findDataDirs(*args, **kwargs):
        for filePattern in filePatterns:
            paths += glob(os.path.join(dir, filePattern))
    return paths
        
# Parse a time string, either a HH:MM:SS string, or a single int/float,
# which is interpreted as a number of minutes, for backwards compatibility.
# Observe that in either 'field' in the HH:MM:SS case, any number is allowed,
# so e.g. 144:5.3:0.01 is interpreted as 144 hours + 5.3 minutes + 0.01 seconds.
def getNumberOfSeconds(timeString):
    parts = timeString.split(":")
    try:
        if len(parts) == 1:  # Backwards compatible, assume single ints/floats means minutes
            return 60 * float(timeString)
        elif len(parts) <= 3:                # Assume format is HH:MM:SS ...
            seconds = 0
            for i in range(len(parts) - 1, -1, -1):
                if (parts[i] != ""): # Handle empty strings (<=:10 gives empty minutes field, for example)
                    seconds += float(parts[i]) * pow(60, len(parts) - 1 - i)
            return seconds
    except ValueError:
        pass
    raise TextTestError, "Illegal time format '" + timeString + \
          "' :  Use format HH:MM:SS or MM:SS, or a single number to denote a number of minutes."

def printWarning(message, stdout=False):
    if stdout:
        if log:
            log.warning("WARNING: " + message)
        else:
            print "WARNING: " + message
    else:
        sys.stderr.write("WARNING: " + message + "\n")

# Useful stuff to handle regular expressions
regexChars = re.compile("[\^\$\[\]\{\}\\\*\?\|\+]")
def isRegularExpression(text):
    return (regexChars.search(text) != None)

# Parse the string as a byte expression.
# Mb/mb/megabytes/mbytes
def parseBytes(text): # pragma: no cover
    lcText = text.lower()
    try:
        # Try this first, to save time if it works
        try:
            return float(text)
        except ValueError:
            pass

        if lcText.endswith("kb") or lcText.endswith("kbytes") or lcText.endswith("k") or lcText.endswith("kilobytes"):
            splitText = lcText.split('k')
            if len(splitText) > 2:
                raise
            return 1000 * float(splitText[0])
        elif lcText.endswith("kib") or lcText.endswith("kibibytes"):
            splitText = lcText.split('k')
            if len(splitText) > 2:
                raise
            return 1024 * float(splitText[0])
        elif lcText.endswith("mb") or lcText.endswith("mbytes") or lcText.endswith("m") or lcText.endswith("megabytes"):
            splitText = lcText.split('m')
            if len(splitText) > 2:
                raise
            return 1000000 * float(splitText[0])
        elif lcText.endswith("mib") or lcText.endswith("mebibytes"):
            splitText = lcText.split('m')
            if len(splitText) > 2:
                raise
            return 1048576 * float(splitText[0])
        elif lcText.endswith("gb") or lcText.endswith("gbytes") or lcText.endswith("g") or lcText.endswith("gigabytes"):
            splitText = lcText.split('g')
            if len(splitText) > 2:
                raise
            return 1000000000 * float(splitText[0])
        elif lcText.endswith("gib") or lcText.endswith("gibibytes"):
            splitText = lcText.split('g')
            if len(splitText) > 2:
                raise
            return 1073741824 * float(splitText[0])
        elif lcText.endswith("tb") or lcText.endswith("tbytes") or lcText.endswith("t") or lcText.endswith("terabytes"):
            splitText = lcText.split('t')
            if len(splitText) > 3:
                raise
            return 1000000000000 * float(splitText[0])
        elif lcText.endswith("tib") or lcText.endswith("tebibytes"):
            splitText = lcText.split('t')
            if len(splitText) > 3:
                raise
            return 1099511627776 * float(splitText[0])
        elif lcText.endswith("pb") or lcText.endswith("pbytes") or lcText.endswith("p") or lcText.endswith("petabytes"):
            splitText = lcText.split('p')
            if len(splitText) > 2:
                raise
            return 10**15 * float(splitText[0])
        elif lcText.endswith("pib") or lcText.endswith("pebibytes"):
            splitText = lcText.split('p')
            if len(splitText) > 2:
                raise
            return 2**50 * float(splitText[0])
        elif lcText.endswith("eb") or lcText.endswith("ebytes") or lcText.endswith("e") or lcText.endswith("exabytes"):
            splitText = lcText.split('e')
            if len(splitText) > 3:
                raise
            return 10**18 * float(splitText[0])
        elif lcText.endswith("eib") or lcText.endswith("exbibytes"):
            splitText = lcText.split('e')
            if len(splitText) > 3:
                raise
            return 2**60 * float(splitText[0])
        elif lcText.endswith("zb") or lcText.endswith("zbytes") or lcText.endswith("z") or lcText.endswith("zettabytes"):
            splitText = lcText.split('z')
            if len(splitText) > 2:
                raise
            return 10**21 * float(splitText[0])
        elif lcText.endswith("zib") or lcText.endswith("zebibytes"):
            splitText = lcText.split('z')
            if len(splitText) > 2:
                raise
            return 2**70 * float(splitText[0])
        elif lcText.endswith("yb") or lcText.endswith("ybytes") or lcText.endswith("y") or lcText.endswith("yottabytes"):
            splitText = lcText.split('y')
            if len(splitText) > 3:
                raise
            return 10**24 * float(splitText[0])
        elif lcText.endswith("yib") or lcText.endswith("yobibytes"):
            splitText = lcText.split('y')
            if len(splitText) > 2:
                raise
            return 2**80 * float(splitText[0])
        else:
            return float(text)
    except:
        raise "Illegal byte format '" + text + "'"

# pango markup doesn't like <,>,& ...
def convertForMarkup(message):
    return message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

class Filter:
    def acceptsTestCase(self, testArg):
        return 1 # pragma: no cover - implemented in all base classes
    def acceptsTestSuite(self, suiteArg):
        return 1
    def acceptsTestSuiteContents(self, suiteArg):
        return 1
    def refine(self, tests):
        return tests

class TextTriggerGroup:
    def __init__(self, texts):
        self.texts = texts
        self.textTriggers = [ TextTrigger(text) for text in self.texts ]

    def stringContainsText(self, searchString):
        for trigger in self.textTriggers:
            if trigger.matches(searchString):
                return True
        return False


class TextFilter(Filter, TextTriggerGroup):
    def __init__(self, filterText, *args):
        TextTriggerGroup.__init__(self, self.parseInput(filterText, *args))

    def parseInput(self, filterText, *args):
        return commasplit(filterText)

    def acceptsTestSuiteContents(self, suite):
        return not suite.isEmpty()


class ApplicationFilter(TextFilter):
    option = "app"
    def acceptsTestCase(self, test):
        return self.acceptsApplication(test.app)
    def acceptsTestSuite(self, suite):
        return self.acceptsApplication(suite.app)
    def acceptsApplication(self, app):
        return self.stringContainsText(app.name)

    
class TestSelectionFilter(TextFilter):
    option = "tp"
    def __init__(self, *args):
        self.diag = logging.getLogger("TestSelectionFilter")
        self.fullSuites = []
        TextFilter.__init__(self, *args)

    def parseInput(self, filterText, app, suites):
        allEntries = TextFilter.parseInput(self, filterText, app, suites)
        if allEntries[0].startswith("appdata="):
            # chopped up per application
            return self.parseForApp(allEntries, app, suites)
        else:
            # old style, one size fits all
            return allEntries

    def parseForApp(self, allEntries, app, suites):
        active = False
        myEntries = []
        toFind = self.getSectionsToFind(allEntries, app, suites)
        self.diag.info("Sections for " + repr(app) + " = " + repr(toFind))
        for entry in allEntries:
            if entry in toFind:
                active = True
            elif entry.startswith("appdata="):
                active = False
            elif active:
                myEntries.append(entry)
        self.diag.info("Found " + repr(myEntries) + " from " + repr(allEntries))
        return myEntries

    def getSectionsToFind(self, allEntries, app, suites):        
        allHeaders = filter(lambda entry: entry.startswith("appdata=" + app.name), allEntries)
        if len(allHeaders) <= 1:
            return allHeaders
        allApps = filter(lambda a: a.name == app.name, [ suite.app for suite in suites ])
        sections = []
        for header in allHeaders:
            versionSet = set(header.split(".")[1:])
            self.diag.info("Looking for app matching " + repr(versionSet))
            bestApp = self.findAppMatchingVersions(versionSet, allApps)
            self.diag.info("Best app for " + header + " = " + repr(bestApp))
            if bestApp is app:
                sections.append(header)

        if len(sections) == 0:
            # We aren't a best-fit for any of them, so we do our best to find one anyway...
            return self.findSectionsMatchingApp(app, allHeaders)
        elif len(sections) == 1:             
            return sections

        return self.findSectionsMatchingApp(app, sections)

    def findSectionsMatchingApp(self, app, allHeaders):
        myVersionSet = set(app.versions)
        def matchKey(header):
            currVersionSet = set(header.split(".")[1:])
            return self.getVersionSetMatchKey(currVersionSet, myVersionSet)

        # Really want some kind of "multimax" here
        bestHeader = max(allHeaders, key=matchKey)
        bestKey = matchKey(bestHeader)
        return filter(lambda h: matchKey(h) == bestKey, allHeaders)

    def getVersionSetMatchKey(self, vset1, vset2):
        return len(vset1.intersection(vset2)), -len(vset1.symmetric_difference(vset2))

    def findAppMatchingVersions(self, myVersionSet, allApps):
        def matchKey(app):
            return self.getVersionSetMatchKey(set(app.versions), myVersionSet)
        return max(allApps, key=matchKey)

    def acceptsTestCase(self, test):
        return test.getRelPath() in self.texts or self.hasFullSuiteAncestor(test.parent)

    def hasFullSuiteAncestor(self, suite):
        return suite in self.fullSuites or (suite.parent and self.hasFullSuiteAncestor(suite.parent))
    
    def acceptsTestSuite(self, suite):
        return self.suiteInTexts(suite) or (suite.parent and self.hasFullSuiteAncestor(suite.parent))

    def suiteInTexts(self, suite):
        if suite.parent is None:
            return True # don't eliminate the root suite :)
        for relPath in self.texts:
            suitePath = suite.getRelPath()
            if relPath == suitePath:
                self.fullSuites.append(suite)
                return True
            elif relPath.startswith(suitePath + "/"):
                return True
        return False


# Generic action to be performed: all actions need to provide these methods
class Action:
    def __call__(self, test):
        pass
    def setUpSuite(self, suite):
        pass
    def setUpApplication(self, app):
        pass
    def tearDownSuite(self, suite):
        pass
    def kill(self, test, sig):
        pass
    def callDuringAbandon(self, testArg):
        # set to True if tests should have this action called even after all is reckoned complete (e.g. UNRUNNABLE)
        return False
    # Useful for printing in a certain format...
    def describe(self, testObj, postText = ""):
        log.info(testObj.getIndent() + repr(self) + " " + repr(testObj) + postText)
    def __str__(self):
        return str(self.__class__)
    @classmethod
    def finalise(cls):
        pass

class ScriptWithArgs(Action):
    def parseArguments(self, args, allowedArgs):
        currKey = ""
        dict = {}
        for arg in args:
            if "=" in arg:
                currKey, val = arg.split("=", 1)
                if currKey in allowedArgs:
                    dict[currKey] = val
                else:
                    print "Unrecognised option '" + currKey + "'"
            elif dict.has_key(currKey):
                dict[currKey] += " " + arg
        return dict

def addCategory(name, briefDesc, longDesc = ""):
    if longDesc:
        TestState.categoryDescriptions[name] = briefDesc, longDesc
    else:
        TestState.categoryDescriptions[name] = briefDesc, briefDesc

# Observer mechanism shouldn't allow for conflicting notifications. Use main thread at all times
class ThreadedNotificationHandler:
    def __init__(self):
        self.workQueue = Queue()
        self.active = False
        self.allowedEvents = []

    def blockEventsExcept(self, allowedEvents):
        self.allowedEvents = allowedEvents

    def enablePoll(self, idleHandleMethod, **kwargs):
        self.active = True
        return idleHandleMethod(self.pollQueue, **kwargs)

    def pollQueue(self):
        try:
            observable, args, kwargs = self.workQueue.get_nowait()
            if len(self.allowedEvents) == 0 or args[0] in self.allowedEvents:
                observable.diagnoseObs("From work queue", *args, **kwargs)
                observable.performNotify(*args, **kwargs)
        except Empty:
            # Idle handler. We must sleep for a bit if we don't do anything, or we use the whole CPU (busy-wait)
            time.sleep(0.1)
        return self.active
    
    def transfer(self, observable, *args, **kwargs):
        self.workQueue.put((observable, args, kwargs))


class Observable:
    threadedNotificationHandler = ThreadedNotificationHandler()
    obsDiag = None
    @classmethod
    def diagnoseObs(klass, message, *args, **kwargs):
        if not klass.obsDiag:
            klass.obsDiag = logging.getLogger("Observable")
        klass.obsDiag.info(message + " " + str(klass) + " " + repr(args) + repr(kwargs))

    def __init__(self, passSelf=False):
        self.observers = []
        self.passSelf = passSelf

    def addObserver(self, observer):
        self.observers.append(observer)

    def setObservers(self, observers):
        self.observers = filter(lambda x: x is not self, observers)

    def inMainThread(self):
        return currentThread().getName() == "MainThread"

    def notify(self, *args, **kwargs):
        if self.threadedNotificationHandler.active and not self.inMainThread():
            self.diagnoseObs("To work queue", *args, **kwargs)
            self.threadedNotificationHandler.transfer(self, *args, **kwargs)
        else:
            self.diagnoseObs("Perform directly", *args, **kwargs)
            self.performNotify(*args, **kwargs)

    def notifyThreaded(self, *args, **kwargs):
        # join the idle handler queue even if we're the main thread
        if self.threadedNotificationHandler.active:
            self.diagnoseObs("To work queue explicitly", *args, **kwargs)
            self.threadedNotificationHandler.transfer(self, *args, **kwargs)
        else:
            self.diagnoseObs("Perform directly", *args, **kwargs)
            self.performNotify(*args, **kwargs)

    def notifyIfMainThread(self, *args, **kwargs):
        if not self.inMainThread():
            return
        else:
            self.diagnoseObs("Perform directly", *args, **kwargs)
            self.performNotify(*args, **kwargs)

    def performNotify(self, name, *args, **kwargs):
        methodName = "notify" + name
        for observer in self.observers:
            if hasattr(observer, methodName):
                self.notifyObserver(observer, methodName, *args, **kwargs)
                
    def notifyObserver(self, observer, methodName, *args, **kwargs):
        # doesn't matter if only some of the observers have the method
        method = getattr(observer, methodName)
        # unpickled objects have not called __init__, and
        # hence do not have self.passSelf ...
        try:
            if hasattr(self, "passSelf") and self.passSelf:
                method(self, *args, **kwargs)
            else:
                method(*args, **kwargs)
        except Exception:
            sys.stderr.write("Observer raised exception while calling " + methodName + " :\n")
            printException()

# Interface all responders must fulfil
class Responder:
    def __init__(self, *args):
        pass
    def addSuites(self, suites):
        for suite in suites:
            self.addSuite(suite)
    # Full suite of tests, get notified of it at the start...
    def addSuite(self, suite):
        pass
    # Called when the state of the test "moves on" in its lifecycle
    def notifyLifecycleChange(self, test, state, changeDesc):
        pass
    # Called when no further actions will be performed on the test
    def notifyComplete(self, test):
        pass
    # Called when everything is finished
    def notifyAllComplete(self):
        pass
    def canBeMainThread(self):
        return True


# Generic state which tests can be in, should be overridden by subclasses
# Acts as a static state for tests which have not run (yet)
# Free text is text of arbitrary length: it will appear in the "Text Info" GUI window when the test is viewed
# and the "details" section in batch mode
# Brief text should be at most two or three words: it appears in the details column in the main GUI window and in
# the summary of batch mode
class TestState(Observable):
    categoryDescriptions = OrderedDict()
    showExecHosts = 0
    def __init__(self, category, freeText = "", briefText = "", started = 0, completed = 0,\
                 executionHosts = [], lifecycleChange = ""):
        Observable.__init__(self)
        self.category = category
        self.freeText = freeText
        self.briefText = briefText
        self.started = started
        self.completed = completed
        self.executionHosts = executionHosts
        self.lifecycleChange = lifecycleChange

    def __str__(self):
        return self.freeText

    def __repr__(self):
        return self.categoryRepr() + self.hostRepr() + self.colonRepr()

    def categoryRepr(self):
        if not self.categoryDescriptions.has_key(self.category):
            return self.category
        longDescription = self.categoryDescriptions[self.category][1]
        return longDescription

    def hostString(self):
        return "on " + ", ".join(self.executionHosts)

    def hostRepr(self):
        if self.showExecHosts and len(self.executionHosts) > 0:
            return " " + self.hostString()
        else:
            return ""

    def colonRepr(self):
        if self.hasSucceeded():
            return ""
        else:
            return " :"

    def getComparisonsForRecalculation(self):
        # Is some aspect of the state out of date
        return []

    # Used by text interface to print states
    def description(self):
        if "\n" in self.freeText:
            return "not compared:\n" + self.freeText
        else:
            return "not compared:  " + self.freeText

    def getFreeText(self):
        return self.freeText # some subclasses might want to calculate this...

    def getTypeBreakdown(self):
        if self.isComplete():
            return "failure", self.briefText
        else:
            return self.category, self.briefText
    def hasStarted(self):
        return self.started or self.completed
    def isComplete(self):
        return self.completed
    def hasSucceeded(self):
        return 0
    def hasFailed(self):
        return self.isComplete() and not self.hasSucceeded()
    def isMarked(self):
        return False
    def hasResults(self):
        # Do we have actual results that can be compared
        return 0
    def shouldAbandon(self):
        return self.lifecycleChange == "complete"
    def isSaveable(self):
        return self.hasFailed() and self.hasResults()
    def warnOnSave(self): #pragma : no cover - only called on saveable tests usually
        return False
    def updateAfterLoad(self, app, **kwargs):
        pass
    def makeModifiedState(self, newRunStatus, newDetails):
        pass
    
            
addCategory("unrunnable", "unrunnable", "could not be run")
addCategory("marked", "marked", "was marked by the user")

class Unrunnable(TestState):
    def __init__(self, freeText, briefText, executionHosts=[], lifecycleChange=""):
        TestState.__init__(self, "unrunnable", freeText, briefText, completed=1, \
                           executionHosts=executionHosts, lifecycleChange=lifecycleChange)
    def shouldAbandon(self):
        return True
    

class MarkedTestState(TestState):
    def __init__(self, freeText, briefText, oldState, executionHosts=[]):
        self.oldState = oldState
        self.myFreeText = freeText
        fullText = freeText + "\n\nORIGINAL STATE:\nTest " + repr(oldState) + "\n " + oldState.freeText
        TestState.__init__(self, "marked", fullText, briefText, completed=1, \
                           executionHosts=executionHosts, lifecycleChange="marked")
        
    # We must implement this ourselves, since we want to be neither successful nor
    # failed, and by default hasFailed is implemented as 'not hasSucceeded()'.
    def hasFailed(self):
        return False

    def hasResults(self):
        return True

    def isMarked(self):
        return True

    def getTypeBreakdown(self):
        return self.category, self.briefText

    def getComparisonsForRecalculation(self):
        # Is some aspect of the state out of date
        return self.oldState.getComparisonsForRecalculation()

    def __getattr__(self, name):
        # Anything not implemented should be called on the actual state...
        return getattr(self.oldState, name)

    def makeNewState(self, *args):
        newOldState = self.oldState.makeNewState(*args)
        return MarkedTestState(self.myFreeText, self.briefText, newOldState, self.executionHosts)
    

log = None
def configureLogging(configFile=None):
    # only set up once
    global log
    if not log:
        if configFile:
            defaults = { "TEXTTEST_PERSONAL_LOG": getPersonalDir("log") }
            logging.config.fileConfig(configFile, defaults)
        log = logging.getLogger("standard log")

def getPersonalConfigDir():
    return os.getenv("TEXTTEST_PERSONAL_CONFIG")

# Return the hostname, guaranteed to be just the hostname...
def gethostname():
    fullname = socket.gethostname()
    return fullname.split(".")[0]

# Return 'localhost' if it is the local host...
def interpretHostname(hostname):
    if hostname == "localhost" or len(hostname) == 0:
        return "localhost"
    localhost = gethostname()
    if hostsMatch(hostname, localhost):
        return "localhost"
    else:
        return hostname

def hostsMatch(hostname, localhost):
    if "@" in hostname:
        user, host = hostname.split("@")
        return hostsMatch(host, localhost) and user == os.getenv("USER")
    else:
        parts = hostname.split(".")
        return parts[0] == localhost
    

# Hacking around os.path.getcwd not working with AMD automounter
def abspath(path):
    if os.environ.has_key("PWD"):
        return os.path.join(os.environ["PWD"], path)
    else:
        return os.path.abspath(path)

# deepcopy(os.environ) still seems to retain links to the actual environment, create a clean copy
def copyEnvironment(values={}, ignoreVars=[]):
    for var, value in os.environ.items():
        if not values.has_key(var) and var not in ignoreVars:
            values[var] = value
    return values

def getInterpreter(executable):
    extension = executable.rsplit(".", 1)[-1]
    cache = { "py" : "python",
              "rb" : "ruby",
              "jar" : "java -jar" }
    return cache.get(extension, "")

def commandLineString(cmdArgs):
    def getQuoteChar(char):
        if char == "\"" and os.name == "posix":
            return "'"
        else:
            return '"'

    def quoteArg(arg):
        if len(arg) == 0:
            return '""'
        quoteChars = "'\"|* "
        for char in quoteChars:
            if char in arg:
                quoteChar = getQuoteChar(char)
                return quoteChar + arg + quoteChar
        return arg.replace("\\", "/")

    return " ".join(map(quoteArg, cmdArgs))

def relpath(fullpath, parentdir):
    normFull = os.path.normpath(fullpath)
    relPath = normFull.replace(os.path.normpath(parentdir), "")
    if relPath != normFull:
        if relPath.startswith(os.sep):
            return relPath[1:]
        else:
            return relPath

def copyPath(srcPath, dstPath):
    if os.path.isdir(srcPath):
        removePath(dstPath)
        shutil.copytree(srcPath, dstPath)
    else:
        shutil.copy(srcPath, dstPath)
        
def removePath(path):
    if os.path.isfile(path) or os.path.islink(path):
        os.remove(path)
        return True
    elif os.path.isdir(path):
        shutil.rmtree(path)
        return True
    else:
        return False

# Useful utility, free text input as comma-separated list which may have spaces
def commasplit(input):
    return map(string.strip, input.split(","))

# Another useful thing that saves an import and remembering weird stuff
def modifiedTime(filename):
    try:
        return os.stat(filename)[stat.ST_MTIME]
    except OSError:
        # Dead links etc.
        return None

# portable version of shlex.split
# See http://sourceforge.net/tracker/index.php?func=detail&aid=1724366&group_id=5470&atid=105470
# As usual, UNIX paths work better on Windows than Windows paths...
def splitcmd(s):
    if os.name == "posix":
        return shlex.split(s)
    else:
        return shlex.split(s.replace("\\", "\\\\"))

# portable version of os.path.samefile
def samefile(writeDir, currDir):
    try:
        return os.path.samefile(writeDir, currDir)
    except Exception: # AttributeError for Windows, OSError if currDir doesn't exist
        # samefile doesn't exist on Windows, but nor do soft links so we can
        # do a simpler version
        return os.path.normpath(writeDir.replace("\\", "/")) == os.path.normpath(currDir.replace("\\", "/"))

def makeWriteable(path):
    currMode = os.stat(path)[stat.ST_MODE]
    currPerm = stat.S_IMODE(currMode)
    newPerm = currPerm | 0220
    os.chmod(path, newPerm)

def getPaths(d):
    paths = [ d ]
    for root, dirs, files in os.walk(d):
        for path in dirs + files:
            fullPath = os.path.join(root, path)
            if not os.path.islink(fullPath):
                # Don't want to / can't change permissions of links anyway
                paths.append(fullPath)
    return paths
    
# Version of rmtree not prone to crashing if directory in use or externally removed
def rmtree(dir, attempts=100):
    realDir = os.path.realpath(dir)
    if not os.path.isdir(realDir):
        log.info("Write directory " + dir + " externally removed")
        return
    # Don't be somewhere under the directory when it's removed
    try:
        if os.getcwd().startswith(realDir):
            root = os.path.dirname(os.path.normpath(dir))
            os.chdir(root)
    except OSError: # pragma: no cover - robustness only
        pass
    for i in range(attempts):
        try:
            shutil.rmtree(realDir)
            return
        except Exception, e:
            if str(e).find("Permission") != -1 or str(e).find("Access") != -1:
                # We own this stuff, don't respect readonly flags set by ourselves, it might just be the SUT doing so...
                for path in getPaths(realDir):
                    try:
                        makeWriteable(path)
                    except OSError, e:
                        log.info("Could not change permissions to be able to remove directory " +
                                 dir + " : - " + str(e))
                        return
                continue
            if os.path.isdir(realDir):
                if i == attempts - 1:
                    log.info("Unable to remove directory " + dir + " :")
                    printException()
                else:
                    log.info("Problems removing directory " + dir + " - waiting 1 second to retry...")
                    time.sleep(1)

class AggregationError(RuntimeError):
    def __init__(self, value1, value2, index):
        self.value1 = value1
        self.value2 = value2
        self.index = index
    

# Useful utility for combining different response values for a series of method calls
class ResponseAggregator:
    def __init__(self, methods):
        self.methods = methods

    def __call__(self, *args, **kwargs):
        if len(self.methods) == 0:
            return
        
        basicValue = self.methods[0](*args, **kwargs)
        for i, extraMethod in enumerate(self.methods[1:]):
            extraValue = extraMethod(*args, **kwargs)
            if type(basicValue) == types.ListType:
                for item in extraValue:
                    if not item in basicValue:
                        basicValue.append(item)
            elif type(basicValue) == types.DictType:
                basicValue.update(extraValue)
            elif extraValue != basicValue:
                raise AggregationError(basicValue, extraValue, i + 1)
                
        return basicValue

def getAggregateString(items, method):
    values = []
    for item in items:
        value = method(item)
        if value not in values:
            values.append(value)
    
    if len(values) > 1:
        return "<default> - " + ",".join(values)
    else:
        return values[0]


def readList(filename):
    try:
        items = []
        for longline in open(filename).readlines():
            line = longline.strip()
            if len(line) > 0 and not line.startswith("#"):
                items.append(line)
        return items
    except IOError:
        return [] # It could be a broken link: don't bail out if so...

emptyLineSymbol = "__EMPTYLINE__"

def readListWithComments(filename, filterMethod=None):
    items = OrderedDict()
    badItems = OrderedDict()
    currComment = ""
    for longline in open(filename).readlines():
        line = longline.strip()
        if len(line) == 0:
            if currComment:
                currComment += emptyLineSymbol + "\n"
            continue
        if line.startswith("#"):
            currComment += longline[1:].lstrip()
        else:
            if filterMethod:
                failReason, warningText = filterMethod(line, items, filename)
                if failReason:
                    currComment += line + " (automatically commented due to " + failReason + ")\n" + emptyLineSymbol + "\n"
                    badItems[line] = warningText
                    continue
            items[line] = currComment.strip()
            currComment = ""
    # Rescue dangling comments in the end (but put them before last test ...)
    if currComment and len(items) > 0:
        items[items.keys()[-1]] = currComment + items[items.keys()[-1]]
    return items, badItems

# comment can contain lines with __EMPTYLINE__ (see above) as a separator
# from free comments, or commented out tests. This method extracts the comment
# after any __EMPTYLINE__s.
def extractComment(comment):
    lastEmptyLinePos = comment.rfind(emptyLineSymbol)
    if lastEmptyLinePos == -1:
        return comment
    else:
        return comment[lastEmptyLinePos + len(emptyLineSymbol) + 1:]

# comment can contain lines with __EMPTYLINE__ (see above) as a separator
# from free comments, or commented out tests. This method replaces the real
# comment for this test with newComment
def replaceComment(comment, newComment):
    lastEmptyLinePos = comment.rfind(emptyLineSymbol)
    if lastEmptyLinePos == -1:
        return newComment
    else:
        return comment[0:lastEmptyLinePos + len(emptyLineSymbol) + 1] + newComment

def openForWrite(path):
    ensureDirExistsForFile(path)
    return open(path, "w")

# Make sure the dir exists
def ensureDirExistsForFile(path):
    dir = os.path.split(path)[0]
    ensureDirectoryExists(dir)

def addLocalPrefix(fullPath, prefix):
    dir, file = os.path.split(fullPath)
    return os.path.join(dir, prefix + "_" + file)

def ensureDirectoryExists(path, attempts=5):
    # os.makedirs seems to be a bit flaky, especially if the file server is loaded
    # or on silly platforms like powerpc. We give it five chances to do its stuff :)
    for attempt in range(attempts):
        if os.path.isdir(path):
            return
        try:
            os.makedirs(path)
        except OSError:
            if attempt == attempts - 1:
                raise

def retryOnInterrupt(function, *args):
    try:
        return function(*args)
    except (IOError, OSError), detail:
        if str(detail).find("Interrupted system call") != -1:
            return retryOnInterrupt(function, *args)
        else:
            raise

def tryFileChange(function, permissionMessage, *args):
    try:
        return function(*args)
    except OSError, e:
        errorStr = str(e)
        if "Permission" in errorStr:
            raise TextTestError, permissionMessage
        else:
            raise TextTestError, errorStr

def getExceptionString():
    type, value, traceback = sys.exc_info()
    return "".join(format_exception(type, value, traceback))

def printException():
    sys.stderr.write("Description of exception thrown :\n")
    exceptionString = getExceptionString()
    sys.stderr.write(exceptionString)
    return exceptionString

def zeroDivisorPercentage(numerator):
    if numerator == 0.0:
        return 0
    else:
        return -1

def calculatePercentageNormalised(oldVal, newVal):        
    largest = max(oldVal, newVal)
    smallest = min(oldVal, newVal)
    if smallest != 0.0:
        return ((largest - smallest) / abs(smallest)) * 100
    else:
        return zeroDivisorPercentage(largest)

def calculatePercentageStandard(oldVal, newVal):        
    if oldVal != 0.0:
        diff = abs(newVal - oldVal)
        return (diff / abs(oldVal)) * 100
    else:
        return zeroDivisorPercentage(newVal)

def roundPercentage(val):
    perc = int(round(val))
    if perc == 0:
        return float("%.0e" % val) # Print one significant figure
    else:
        return perc


class PreviewGenerator:
    def __init__(self, maxWidth, maxLength):
        self.maxWidth = maxWidth
        self.maxLength = maxLength

    def getCutLines(self, lines):
        if len(lines) < self.maxLength:
            return lines
        else:
            return lines[:self.maxLength] + [ "<truncated after showing first " + pluralise(self.maxLength, "line") + ">\n" ]

    def getPreview(self, file):
        fileLines = retryOnInterrupt(self.getFileLines, file)
        return self.getPreviewFromLines(fileLines)

    def getFileLines(self, file):
        lines = file.readlines()
        file.close()
        return lines

    def getPreviewFromLines(self, lines):
        cutLines = self.getCutLines(lines)
        lines = map(self.getWrappedLine, cutLines)
        return "".join(lines)

    def getWrappedLine(self, line):
        remaining = line
        result = ""
        while True:
            if len(remaining) <= self.maxWidth:
                return result + remaining
            result += remaining[:self.maxWidth] + "\n"
            remaining = remaining[self.maxWidth:]


# Exception to throw. It's generally good to throw this internally
class TextTestError(RuntimeError):
    pass

class TextTestWarning(RuntimeError):
    pass

# Sort of a workaround to get e.g. CVSLogInGUI to show a message in a simple info dialog
class TextTestInformation(RuntimeError):
    pass

# Yes, we know that getopt exists. However it throws exceptions when it finds unrecognised things, and we can't do that...
class OptionFinder(OrderedDict):
    def __init__(self, args, defaultKey = "default"):
        OrderedDict.__init__(self)
        self.buildOptions(args, defaultKey)
    def buildOptions(self, args, defaultKey):
        optionKey = None
        for item in args:
            if item.startswith("-"):
                optionKey = self.stripMinuses(item)
                self[optionKey] = None
            elif optionKey:
                if self[optionKey] is not None:
                    self[optionKey] += " "
                else:
                    self[optionKey] = ""
                self[optionKey] += item.strip()
            else:
                self[defaultKey] = item
    def stripMinuses(self, item):
        if len(item) > 1 and item[1] == "-":
            return item[2:].strip()
        else:
            return item[1:].strip()

class TextTrigger:
    def __init__(self, text):
        self.text = text
        self.regex = None
        if isRegularExpression(text):
            try:
                self.regex = re.compile(text)
            except re.error:
                pass
    def __repr__(self):
        return self.text
    def matches(self, line, *args):
        if self.regex:
            return self.regex.search(line)
        else:
            return line.find(self.text) != -1
    def replace(self, line, newText):
        if self.regex:
            return re.sub(self.text, newText, line)
        else:
            return line.replace(self.text, newText)

# Used for application and personal configuration files
class MultiEntryDictionary(OrderedDict):
    warnings = []
    def __init__(self, importKey="", importFileFinder=None, aliases={}, *args, **kw):
        OrderedDict.__init__(self, *args, **kw)
        self.diag = logging.getLogger("MultiEntryDictionary")
        self.aliases = aliases
        self.importKey = importKey
        self.importFileFinder= importFileFinder

    def __reduce__(self):
        # Need this because of __reduce__ in OrderedDict
        # which merrily reduces all the attributes of the subclass without asking
        # Used when doing deepcopy()
        items = [[k, self[k]] for k in self]
        return self.__class__, (self.importKey, Callable(self.importFileFinder), self.aliases, items)
        
    def getSectionInfo(self, sectionName=""):
        if sectionName and sectionName != "end":
            return self[sectionName], sectionName
        else:
            return self, "<global>"

    def setAlias(self, aliasName, realName):
        self.aliases[aliasName] = realName

    def getEntryName(self, fromConfig):
        return self.aliases.get(fromConfig, fromConfig)

    def readValues(self, fileNames, *args, **kwargs):
        for filename in fileNames:
            self.readFromFile(filename, *args, **kwargs)

    def readFromFile(self, filename, *args, **kwargs):
        self.diag.info("Reading file " + filename)
        currSectionName = ""
        for line in readList(filename):
            if self.isSectionHeader(line):
                currSectionName = self.getNewSectionInfo(line, *args, **kwargs)
            elif ":" in line:
                self.parseConfigLine(line, currSectionName, *args, **kwargs)
            else:
                self.warn("Could not parse config line " + line)

    def isSectionHeader(self, line):
        return line.startswith("[") and line.endswith("]")

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)
            printWarning(message)

    def parseConfigLine(self, line, currSectionName, *args, **kwargs):
        key, value = line.split(":", 1)
        entryName = self.getEntryName(string.Template(key).safe_substitute(os.environ))
        self.addEntry(entryName, value, currSectionName, *args, **kwargs)
        if key and key == self.importKey:
            self.readFromFile(self.importFileFinder(os.path.expandvars(value)), *args, **kwargs)
            
    def getNewSectionInfo(self, line, insert=True, errorOnUnknown=False):
        name = self.getEntryName(line[1:-1])
        if name != "end":
            if self.has_key(name):
                value = self[name]
                if isinstance(value, OrderedDict) or type(value) == types.DictType:
                    return name
                else:
                    self.warn("Config entry name '" + name + "' incorrectly used as a section marker.")
            elif insert:
                self[name] = OrderedDict()
                return name
            elif errorOnUnknown:
                self.warn("Config section name '" + name + "' not recognised.")
        return ""
        
    def addEntry(self, entryName, entry, sectionName="", *args, **kwargs):
        currDict, currSection = self.getSectionInfo(sectionName)
        try:
            self._addEntry(entryName, entry, currDict, currSection, *args, **kwargs)
        except ValueError:
            self.warn("Config entry name '" + entryName + "' in section '" + currSection +
                      "' given an invalid value '" + entry + "', ignoring.")

    def removeEntry(self, entryName, entry, sectionName=""):
        currDict, currSection = self.getSectionInfo(sectionName)
        if entryName in currDict:
            dictElem = currDict[entryName]
            if entry in dictElem:
                dictElem.remove(entry)
            
    def _addEntry(self, entryName, entry, currDict, currSection, insert=True, errorOnUnknown=False):
        if currDict is not self and self.has_key(entryName):
            self.warn("Config entry name '" + entryName + "' found in section '" + currSection +
                      "', but defined at global scope. Did you forget an [end] marker?")

        entryExists = currDict.has_key(entryName)
        if entryExists:
            self.diag.info("Entry existed, setting " + entryName + "=" + entry)
            self.insertEntry(entryName, entry, currDict)
        else:
            if insert or not currDict is self:
                self.diag.info("Inserting " + entryName + "=" + repr(entry))
                currDict[entryName] = self.castEntry(entryName, entry, currDict)
            elif errorOnUnknown:
                self.warn("Config entry name '" + entryName + "' not recognised.")

    def getDictionaryValueType(self, currDict):
        val = currDict.values()
        if len(val) == 0:
            return types.StringType
        else:
            return type(val[0])

    def castEntry(self, dummy, entry, currDict):
        if type(entry) != types.StringType:
            return entry
        dictValType = self.getDictionaryValueType(currDict)
        if dictValType == types.ListType:
            return self.getBasicList(entry)
        else:
            return dictValType(entry)

    def getBasicList(self, entry):
        if entry.startswith("{CLEAR"):
            return []
        else:
            return [ entry ]

    def getListValue(self, entry, currentList):
        if entry == "{CLEAR LIST}":
            return []
        elif entry.startswith("{CLEAR"):
            itemToRemove = entry[7:-1]
            if itemToRemove in currentList:
                currentList.remove(itemToRemove)
        elif entry not in currentList:
            self.diag.info("Get list value for " + entry + repr(currentList))
            currentList.append(entry)
        return currentList

    def insertEntry(self, entryName, entry, currDict):
        currType = type(currDict[entryName])
        if currType == types.ListType:
            currDict[entryName] = self.getListValue(entry, currDict[entryName])
        elif currType == types.DictType:
            newCurrDict = self.getSectionInfo(entryName)[0]
            if "default" in newCurrDict:
                self.insertEntry("default", entry, newCurrDict)
            else:
                self.warn("Config entry name '" + entryName + "' is only valid as a section marker.")
        else:
            currDict[entryName] = currType(entry)

    def getSingle(self, key, expandVars=True, envMapping=os.environ):
        value = self.get(key)
        if expandVars:
            return self.expandEnvironment(value, envMapping)
        else:
            return value

    def getComposite(self, key, subKey, expandVars=True, envMapping=os.environ, defaultKey="default"):
        value = self.getCompositeUnexpanded(key, subKey, defaultKey)
        if expandVars:
            return self.expandEnvironment(value, envMapping)
        else:
            return value

    def getCompositeUnexpanded(self, key, subKey, defaultSubKey="default"):
        dict = self.get(key)
        # If it wasn't a dictionary, return None
        if not hasattr(dict, "items"):
            return None
        listVal = []
        usingList = False
        for currSubKey, currValue in dict.items():
            if fnmatch.fnmatch(subKey, currSubKey):
                if type(currValue) == types.ListType:
                    listVal += currValue
                    usingList = True
                else:
                    return currValue
        # A certain amount of duplication here - hard to see how to avoid it
        # without compromising performance though...
        if subKey != defaultSubKey:
            defValue = dict.get(defaultSubKey)
            if defValue is not None:
                if type(defValue) == types.ListType:
                    listVal += defValue
                    return listVal
                else:
                    return defValue
        if usingList:
            return listVal

    @classmethod
    def expandEnvironment(cls, value, envMapping):
        if isinstance(value, str):
            return string.Template(value).safe_substitute(envMapping)
        elif isinstance(value, list):
            return [ string.Template(element).safe_substitute(envMapping) for element in value ]
        elif isinstance(value, dict):
            newDict = {}
            for key, val in value.items():
                newDict[key] = cls.expandEnvironment(val, envMapping)
            return newDict
        else:
            return value


class Option:
    def __init__(self, name, value, description, changeMethod):
        self.name = name
        self.defaultValue = value
        self.valueMethod = None
        self.updateMethod = None
        self.description = description
        self.changeMethod = changeMethod
        
    def getValue(self):
        if self.valueMethod:
            try:
                return self.valueMethod()
            except ValueError:
                self.valueMethod = None

        return self.defaultValue

    def resetDefault(self):
        if self.valueMethod:
            value = self.valueMethod()
            if value is not None:
                self.defaultValue = value
                self.valueMethod = None
            
    def getCmdLineValue(self):
        return self.getValue()

    def setValue(self, value):
        self.defaultValue = value
        if self.updateMethod:
            self.updateMethod(value)

    def setMethods(self, valueMethod, updateMethod):
        self.valueMethod = valueMethod
        self.updateMethod = updateMethod

    def reset(self):
        if self.updateMethod:
            self.updateMethod(self.defaultValue)
        else:
            self.valueMethod = None

    def addPossibleValue(self, value):
        pass
        

class TextOption(Option):
    def __init__(self, name, value="", possibleValues=[], allocateNofValues=-1,
                 selectDir=False, selectFile=False, saveFile=False, possibleDirs=[],
                 description="", changeMethod=None, multilineEntry=False):
        Option.__init__(self, name, value, description, changeMethod)
        self.possValAppendMethod = None
        self.possValListMethod = None
        self.possibleValues = []
        self.nofValues = allocateNofValues
        self.selectDir = selectDir
        self.selectFile = selectFile
        self.saveFile = saveFile
        self.possibleDirs = possibleDirs
        self.clearMethod = None
        self.multilineEntry = multilineEntry
        self.setPossibleValues(possibleValues)
        
    def setPossibleValuesMethods(self, appendMethod, getMethod):
        self.possValListMethod = getMethod
        if appendMethod:
            self.possValAppendMethod = appendMethod
            self.updatePossibleValues()

    def updatePossibleValues(self):
        if self.possValAppendMethod:
            for value in self.possibleValues:
                self.possValAppendMethod(value)

    def listPossibleValues(self):
        if self.possValListMethod:
            return self.possValListMethod()
        else:
            return self.possibleValues

    def addPossibleValue(self, value):
        if value not in self.possibleValues:
            self.possibleValues.append(value)
            
    def setValue(self, value):
        Option.setValue(self, value)
        if self.usePossibleValues():
            self.setPossibleValues(self.possibleValues)

    def setPossibleValues(self, values):
        if self.selectFile or (self.defaultValue in values):
            self.possibleValues = values
        else:
            self.possibleValues = [ self.defaultValue ] + values
        self.clear()
        self.updatePossibleValues()

    def getPossibleDirs(self):
        if self.selectDir or self.selectFile:
            return self.possibleDirs + self.possibleValues
        else:
            return self.possibleDirs

    def usePossibleValues(self):
        return self.selectDir or self.nofValues > 1 or len(self.possibleValues) > 1

    def setClearMethod(self, clearMethod):
        self.clearMethod = clearMethod

    def clear(self):
        if self.clearMethod:
            self.clearMethod()

    def getValue(self):
        basic = Option.getValue(self)
        if (self.selectFile or self.saveFile or self.selectDir) and basic:
            # If files are returned, turn the paths into UNIX format...
            return basic.replace("\\", "/")
        else:
            return basic

    def getDirectories(self):
        allDirs = self.getPossibleDirs()
        for dir in allDirs:
            try:
                ensureDirectoryExists(dir)
            except OSError: # Might not have permissions
                allDirs.remove(dir)
                
        return allDirs, self.findDefaultDirectory(allDirs)

    def canBeDefaultDir(self, dir):
        return self.saveFile or len(os.listdir(dir)) > 0

    def getPreviousDirectory(self):
        prevVal = self.getValue()
        if prevVal and os.path.exists(prevVal):
            if self.selectDir:
                return prevVal
            else:
                return os.path.dirname(prevVal)

    def findDefaultDirectory(self, allDirs):
        previousDir = self.getPreviousDirectory()
        if previousDir in allDirs and self.canBeDefaultDir(previousDir):
            return previousDir
        
        # Set first non-empty dir as default ...)
        for dir in allDirs:
            if self.canBeDefaultDir(dir):
                return dir

        return allDirs[0]

class Switch(Option):
    def __init__(self, name="", value=0, options=[], hideOptions=False, description="", changeMethod = None):
        Option.__init__(self, name, int(value), description, changeMethod)
        self.options = options
        self.hideOptions = hideOptions

    def setValue(self, value):
        Option.setValue(self, int(value))

    def getValue(self):
        return int(Option.getValue(self))

    def toggle(self):
        self.setValue(1 - self.getValue())

    def getCmdLineValue(self):
        if len(self.options) > 2:
            return str(self.getValue())
        else:
            return "" # always on or off...


class OptionGroup:
    def __init__(self, name):
        self.name = name
        self.options = OrderedDict()
        
    def reset(self):
        for option in self.options.values():
            option.reset()

    def setValue(self, key, value):
        if self.options.has_key(key):
            self.options[key].setValue(value)
            return True
        else:
            return False #pragma : no cover - should never happen

    def getValue(self, key, defValue = None):
        if self.options.has_key(key):
            return self.options[key].getValue()
        else:
            return defValue

    # For back compatibility
    setOptionValue = setValue
    setSwitchValue = setValue
    getOptionValue = getValue
    getSwitchValue = getValue

    def addSwitch(self, key, *args, **kwargs):
        if self.options.has_key(key):
            return False
        self.options[key] = Switch(*args, **kwargs)
        return True

    def addOption(self, key, *args, **kwargs):
        if self.options.has_key(key):
            return False
        self.options[key] = TextOption(*args, **kwargs)
        return True

    def setPossibleValues(self, key, possibleValues):
        option = self.options.get(key)
        if option:
            option.setPossibleValues(possibleValues)
            
    def getOption(self, key):
        return self.options.get(key)

    def getOptionValueMap(self):
        values = {}
        for key, option in self.options.items():
            value = option.getValue()
            if value:
                values[key] = option.getValue()
        return values

    def keys(self):
        return self.options.keys()

    def getOptionsForCmdLine(self, onlyKeys):
        commandLines = []
        for key, option in self.options.items():
            if self.accept(key, option, onlyKeys):
                commandLines.append((key, option.getCmdLineValue()))
        return commandLines
    
    def moveToEnd(self, keys):
        for key in keys:
            option = self.options.pop(key)
            self.options[key] = option

    def accept(self, key, option, onlyKeys):
        value = option.getValue()
        if not value or (isinstance(value, str) and value.startswith("<default>")):
            return False
        if len(onlyKeys) == 0:
            return True
        return key in onlyKeys
    

