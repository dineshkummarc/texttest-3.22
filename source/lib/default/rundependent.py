#!/usr/bin/env python


import os

if __name__ == "__main__":
    import sys
    libDir = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
    sys.path.insert(0, libDir)

import plugins, fpdiff, logging, shutil
from optparse import OptionParser
from StringIO import StringIO

class Filtering(plugins.TestState):
    def __init__(self, name, **kw):
        plugins.TestState.__init__(self, name, briefText="", **kw)    
        
# Generic base class for filtering standard and temporary files
class FilterAction(plugins.Action):
    def __init__(self, useFilteringStates=False):
        self.diag = logging.getLogger("Filter Actions")
        self.useFilteringStates = useFilteringStates
    def __call__(self, test):
        if self.useFilteringStates:
            self.changeToFilteringState(test)
            
        for fileName, postfix in self.filesToFilter(test):
            self.diag.info("Considering for filtering : " + fileName)
            stem = self.getStem(fileName)
            newFileName = test.makeTmpFileName(stem + "." + test.app.name + postfix, forFramework=1)
            self.performAllFilterings(test, stem, fileName, newFileName)

    def getStem(self, fileName):
        return os.path.basename(fileName).split(".")[0]

    def changeToFilteringState(self, *args): # pragma: no cover - documentation only
        pass

    def performAllFilterings(self, test, stem, fileName, newFileName):
        currFileName = fileName
        filters = self.makeAllFilters(test, stem, test.app)
        for fileFilter, extraPostfix in filters:
            writeFileName = newFileName + extraPostfix
            self.diag.info("Applying " + fileFilter.__class__.__name__ + " to make\n" + writeFileName + " from\n " + currFileName) 
            if os.path.isfile(writeFileName):
                self.diag.info("Removing previous file at " + writeFileName)
                os.remove(writeFileName)
            currFile = open(currFileName, "rU") # use universal newlines to simplify
            writeFile = plugins.openForWrite(writeFileName)
            fileFilter.filterFile(currFile, writeFile)
            writeFile.close()
            currFileName = writeFileName
        if len(filters) > 0 and currFileName != newFileName:
            shutil.move(currFileName, newFileName)

    def getFilteredText(self, test, fileName, app):
        stem = self.getStem(fileName)
        filters = self.makeAllFilters(test, stem, app)
        inFile = open(fileName)
        if len(filters) == 0:
            try:
                return inFile.read()
            finally:
                inFile.close()
        for fileFilter, _ in filters:
            self.diag.info("Applying " + fileFilter.__class__.__name__ + " to " + fileName) 
            outFile = StringIO()
            fileFilter.filterFile(inFile, outFile)
            inFile.close()
            inFile = outFile
            inFile.seek(0)
        value = outFile.getvalue()
        outFile.close()
        return value
        
    def makeAllFilters(self, test, stem, app):
        filters = self._makeAllFilters(test, stem, app)
        if len(filters) == 0 and self.changedOs(app):
            return  [ (RunDependentTextFilter([], ""), "") ]
        else:
            return filters

    def _makeAllFilters(self, test, stem, app):                    
        filters = []
        configObj = test
        if test.app is not app: # happens when testing filtering in the static GUI
            configObj = app
        runDepTexts = configObj.getCompositeConfigValue("run_dependent_text", stem)
        if runDepTexts:
            filters.append((RunDependentTextFilter(runDepTexts, test.getRelPath()), ".normal"))

        unorderedTexts = configObj.getCompositeConfigValue("unordered_text", stem)
        if unorderedTexts:
            filters.append((UnorderedTextFilter(unorderedTexts, test.getRelPath()), ".sorted"))
        return filters
            
    def changedOs(self, app):
        homeOs = app.getConfigValue("home_operating_system")
        return homeOs != "any" and os.name != homeOs

    def constantPostfix(self, files, postfix):
        return [ (file, postfix) for file in files ]
        

class FilterOriginal(FilterAction):
    def filesToFilter(self, test):
        resultFiles, defFiles = test.listStandardFiles(allVersions=False, defFileCategory="regenerate")
        return self.constantPostfix(resultFiles + defFiles, "origcmp")

    def changeToFilteringState(self, test):
        # Notifications of current status are only useful when doing normal filtering in the GUI
        execMachines = test.state.executionHosts
        freeText = "Filtering stored result files on " + ",".join(execMachines)
        test.changeState(Filtering("initial_filter", executionHosts=execMachines,
                                   freeText=freeText, lifecycleChange="start initial filtering"))

    
class FilterTemporary(FilterAction):
    def filesToFilter(self, test):
        return self.constantPostfix(test.listTmpFiles(), "cmp")

    def _makeAllFilters(self, test, stem, app):
        filters = FilterAction._makeAllFilters(self, test, stem, app)
        floatTolerance = app.getCompositeConfigValue("floating_point_tolerance", stem)
        relTolerance = app.getCompositeConfigValue("relative_float_tolerance", stem)
        if floatTolerance or relTolerance:
            origFile = test.makeTmpFileName(stem + "." + app.name + "origcmp", forFramework=1)
            if not os.path.isfile(origFile):
                origFile = test.getFileName(stem)
            if origFile and os.path.isfile(origFile):
                filters.append((FloatingPointFilter(origFile, floatTolerance, relTolerance), ".fpdiff"))
        return filters

    def changeToFilteringState(self, test):
        # Notifications of current status are only useful when doing normal filtering in the GUI
        execMachines = test.state.executionHosts
        freeText = "Filtering and comparing newly generated result files on " + ",".join(execMachines)
        newState = Filtering("final_filter", executionHosts=execMachines, started=1,
                             freeText=freeText, lifecycleChange="start final filtering and comparison")
        if test.state.category == "killed":
            newState.failedPrediction = test.state
        test.changeState(newState)


class FilterErrorText(FilterAction):
    def _makeAllFilters(self, test, stem, app):
        texts = app.getConfigValue("suppress_stderr_text")
        return [ (RunDependentTextFilter(texts), "") ]
    

class FilterProgressRecompute(FilterAction):
    def filesToFilter(self, test):
        return self.constantPostfix(test.listTmpFiles(), "partcmp")


class FilterResultRecompute(FilterAction):
    def filesToFilter(self, test):
        result = []
        for fileComp in test.state.allResults:
            # Either of these files might have disappeared
            if fileComp.stdFile and os.path.isfile(fileComp.stdFile):
                result.append((fileComp.stdFile, "origcmp"))
            if fileComp.tmpFile and os.path.isfile(fileComp.tmpFile):
                result.append((fileComp.tmpFile, "cmp"))
        return result

class FloatingPointFilter:
    def __init__(self, origFileName, tolerance, relative):
        self.origFileName = origFileName
        self.tolerance, self.relative = None, None
        if tolerance:
            self.tolerance = tolerance
        if relative:
            self.relative = relative

    def filterFile(self, inFile, writeFile):
        fromlines = open(self.origFileName, "rU").readlines()
        tolines = inFile.readlines()
        fpdiff.fpfilter(fromlines, tolines, writeFile, self.tolerance, self.relative)


class RunDependentTextFilter(plugins.Observable):
    def __init__(self, filterTexts, testId=""):
        plugins.Observable.__init__(self)
        self.diag = logging.getLogger("Run Dependent Text")
        self.lineFilters = [ LineFilter(text, testId, self.diag) for text in filterTexts ]

    def filterFile(self, file, newFile, filteredAway=None):
        lineNumber = 0
        lengths = []
        for line in file:
            # We don't want to stack up ActionProgreess calls in ThreaderNotificationHandler ...
            self.notifyIfMainThread("ActionProgress")
            lineNumber += 1
            lineFilter, filteredLine, removeCount = self.getFilteredLine(line, lineNumber)
            if removeCount:
                offset = sum(lengths[-removeCount:])
                newFile.seek(-offset, os.SEEK_CUR)
                newFile.truncate()
                lengths = []
            if filteredLine:
                newFile.write(filteredLine)
                lengths.append(len(filteredLine))
            elif filteredAway is not None and lineFilter is not None:
                filteredAway.setdefault(lineFilter, []).append(line)

    def getFilteredLine(self, line, lineNumber):
        for lineFilter in self.lineFilters:
            changed, filteredLine, removeCount = lineFilter.applyTo(line, lineNumber)
            if changed:
                if not filteredLine:
                    return lineFilter, filteredLine, removeCount
                line = filteredLine
        return None, line, 0


class UnorderedTextFilter(RunDependentTextFilter):
    def filterFile(self, file, newFile):
        unorderedLines = {}
        RunDependentTextFilter.filterFile(self, file, newFile, unorderedLines)
        self.writeUnorderedText(newFile, unorderedLines)

    def writeUnorderedText(self, newFile, lines):
        for filter in self.lineFilters:
            unordered = lines.get(filter, [])
            if len(unordered) == 0:
                continue
            unordered.sort()
            newFile.write("-- Unordered text as found by filter '" + filter.originalText + "' --" + "\n")
            for line in unordered:
                newFile.write(line)
            newFile.write("\n")
  

class LineNumberTrigger:
    def __init__(self, lineNumber):
        self.lineNumber = lineNumber
    def __repr__(self):
        return "Line number trigger for line " + str(self.lineNumber)
    def matches(self, lineArg, lineNumber):
        return lineNumber == self.lineNumber
    def replace(self, lineArg, newText):
        return newText + "\n"

def getWriteDirRegexp(testId):
    # Some stuff, a date, and the testId (ignore the appId as we don't know when or where)
    # Doesn't handle paths with spaces, which seems hard, but does hardcode the default location of $HOME on Windows...
    posixVersion = '([A-Za-z]:/Documents and Settings)?[^ "=]*/[^ "=]*[0-3][0-9][A-Za-z][a-z][a-z][0-9]{6}[^ "=]*/' + testId
    return posixVersion.replace("/", "[/\\\\]")

class LineFilter:
    dividers = [ "{->}", "{[->]}", "{[->}", "{->]}" ]
    # All syntax that affects how a match is found
    matcherStrings = [ "{LINE ", "{INTERNAL " ]
    # All syntax that affects what is done when a match is found
    matchModifierStrings = [ "{WORD ", "{REPLACE ", "{LINES ", "{PREVLINES " ]
    internalExpressions = { "writedir" : getWriteDirRegexp }
    def __init__(self, text, testId, diag):
        self.originalText = text
        self.testId = testId
        self.diag = diag
        self.trigger = None
        self.untrigger = None
        self.linesToRemove = 1
        self.prevLinesToRemove = 0
        self.autoRemove = 0
        self.wordNumber = None
        self.replaceText = None
        self.divider = None
        self.removeWordsAfter = 0
        self.parseOriginalText()
        self.diag.info("Created trigger : " + repr(self.trigger))
        
    def getInternalExpression(self, parameter):
        method = self.internalExpressions.get(parameter)
        return method(self.testId)
    
    def makeRegexTrigger(self, parameter):
        expression = self.getInternalExpression(parameter)
        return plugins.TextTrigger(expression)

    def parseOriginalText(self):
        for divider in self.dividers:
            dividerPoint = self.originalText.find(divider)
            if dividerPoint != -1:
                beforeText, afterText, _ = self.extractParameter(self.originalText, dividerPoint, divider)
                self.divider = divider
                self.trigger = self.parseText(beforeText)
                self.untrigger = self.parseText(afterText)
                return
        self.trigger = self.parseText(self.originalText)
        
    def parseText(self, text):
        for matchModifierString in self.matchModifierStrings:
            linePoint = text.find(matchModifierString)
            if linePoint != -1:
                beforeText, afterText, parameter = self.extractParameter(text, linePoint, matchModifierString)
                self.readMatchModifier(matchModifierString, parameter)
                text = beforeText + afterText
        matcherString, parameter = self.findMatcherInfo(text)
        return self.createTrigger(matcherString, parameter)

    def findMatcherInfo(self, text):
        for matcherString in self.matcherStrings:
            linePoint = text.find(matcherString)
            if linePoint != -1:
                parameter = self.extractParameter(text, linePoint, matcherString)[-1]
                return matcherString, parameter
        return "", text

    def extractParameter(self, textToParse, linePoint, syntaxString):
        beforeText = textToParse[:linePoint]
        afterText = textToParse[linePoint + len(syntaxString):]
        endPos = afterText.find("}")
        parameter = afterText[:endPos]
        afterText = afterText[endPos + 1:]
        return beforeText, afterText, parameter
    
    def readMatchModifier(self, matchModifierString, parameter):
        if matchModifierString == "{REPLACE ":
            self.replaceText = parameter
        elif matchModifierString == "{WORD ":
            if parameter.endswith("+"):
                self.removeWordsAfter = 1
                self.wordNumber = int(parameter[:-1])
            else:
                self.wordNumber = int(parameter)
            # Somewhat non-intuitive to count from 0...
            if self.wordNumber > 0:
                self.wordNumber -= 1
        elif matchModifierString == "{LINES ":
            self.linesToRemove = int(parameter)
        elif matchModifierString == "{PREVLINES ":
            self.prevLinesToRemove = int(parameter)

    def createTrigger(self, matcherString, parameter):
        if matcherString == "{LINE ":
            return LineNumberTrigger(int(parameter))
        elif matcherString == "{INTERNAL " and self.internalExpressions.has_key(parameter):
            return self.makeRegexTrigger(parameter)
        else:
            return plugins.TextTrigger(parameter)

    def applyTo(self, line, lineNumber=0):
        if self.autoRemove:
            return self.applyAutoRemove(line)

        if self.trigger.matches(line, lineNumber):
            self.diag.info(repr(self.trigger) + " matched " + line.strip())
            return self.applyMatchingTrigger(line)
        else:
            return False, line, 0
        
    def applyAutoRemove(self, line):
        if self.untrigger:
            if self.untrigger.matches(line.strip()):
                self.diag.info(repr(self.untrigger) + " (end) matched " + line.strip()) 
                self.autoRemove = 0
                if self.divider.endswith("]}"):
                    return True, None, 0
                else:
                    return False, line, 0
        else:
            self.autoRemove -= 1
        return True, self.filterWords(line), 0

    def applyMatchingTrigger(self, line):
        if self.untrigger:
            self.autoRemove = 1
            return self.divider.startswith("{["), self.filterWords(line), 0
        if self.linesToRemove:
            self.autoRemove = self.linesToRemove - 1
        return True, self.filterWords(line, self.trigger), self.prevLinesToRemove
            
    def filterWords(self, line, trigger=None):
        if self.wordNumber != None:
            words = line.rstrip().split(" ")
            self.diag.info("Removing word " + str(self.wordNumber) + " from " + repr(words))
            realNumber = self.findRealWordNumber(words)
            self.diag.info("Real number was " + str(realNumber))
            if realNumber < len(words):
                if self.removeWordsAfter:
                    words = words[:realNumber]
                    if self.replaceText:
                        words.append(self.replaceText)
                else:
                    if self.replaceText:
                        words[realNumber] = self.replaceText
                    else:
                        del words[realNumber]
            return " ".join(words).rstrip() + "\n"
        elif trigger and self.replaceText != None:
            return trigger.replace(line, self.replaceText)

    def findRealWordNumber(self, words):
        if self.wordNumber < 0:
            return self.findRealWordNumberBackwards(words)
        wordNumber = 0
        for realWordNumber in range(len(words)):
            if len(words[realWordNumber]):
                if wordNumber == self.wordNumber:
                    return realWordNumber
                wordNumber += 1
        return len(words) + 1
    def findRealWordNumberBackwards(self, words):
        wordNumber = -1
        for index in range(len(words)):
            realWordNumber = -1 - index
            word = words[realWordNumber]
            if len(word):
                if wordNumber == self.wordNumber:
                    return realWordNumber
                wordNumber -= 1
        return len(words) + 1

if __name__ == "__main__":
    parser = OptionParser("usage: %prog [options] filter1 filter2 ...")
    parser.add_option("-m", "--module",
                      help="also import module MODULE", metavar="MODULE")
    parser.add_option("-u", "--unordered", action="store_true", 
                      help='Use unordered filter instead of standard one')
    parser.add_option("-t", "--testrelpath", 
                      help="use test relative path RELPATH", metavar="RELPATH")
    (options, args) = parser.parse_args()
    if options.module:
        sys.modules["default.rundependent"] = sys.modules["__main__"]
        sys.path.insert(0, os.path.join(libDir, "../site/lib"))
        exec "import " + options.module
    allPaths = plugins.findDataPaths([ "logging.console" ], dataDirName="log", includePersonal=True)
    plugins.configureLogging(allPaths[-1]) # Won't have any effect if we've already got a log file
    if options.unordered:
        runDepFilter = UnorderedTextFilter(args, options.testrelpath)
    else:
        runDepFilter = RunDependentTextFilter(args, options.testrelpath)
    runDepFilter.filterFile(sys.stdin, sys.stdout)
