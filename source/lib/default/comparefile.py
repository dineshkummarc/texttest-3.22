#!/usr/local/bin/python


import os, filecmp, plugins, time, subprocess, logging
from shutil import copyfile

class FileComparison:
    SAME = 0
    DIFFERENT = 1
    SAVED = 2
    def __init__(self, test, stem, standardFile, tmpFile, testInProgress=False, **kw):
        self.stdFile = standardFile
        self.stdCmpFile = self.stdFile
        self.tmpFile = tmpFile
        self.tmpCmpFile = tmpFile
        self.stem = stem
        self.differenceCache = self.SAME
        self.recalculationTime = None
        self.diag = logging.getLogger("FileComparison")
        self.severity = test.getCompositeConfigValue("failure_severity", self.stem)
        self.displayPriority = test.getCompositeConfigValue("failure_display_priority", self.stem)
        maxLength = test.getConfigValue("lines_of_text_difference")
        maxWidth = test.getConfigValue("max_width_text_difference")
        # It would be nice if this could be replaced by some automagic file type detection
        # mechanism, such as the *nix 'file' command, but as the first implementation I've
        # chosen to use a manually created list instead.
        self.binaryFile = test.configValueMatches("binary_file", self.stem)
        self.previewGenerator = plugins.PreviewGenerator(maxWidth, maxLength)
        self.textDiffTool = test.getConfigValue("text_diff_program")
        self.textDiffToolMaxSize = plugins.parseBytes(test.getCompositeConfigValue("max_file_size", self.textDiffTool))
        self.freeTextBody = None
        # subclasses may override if they don't want to store in this way
        self.cacheDifferences(test, testInProgress)
        self.diag.info("Created file comparison std: " + repr(self.stdFile) + " tmp: " +
                       repr(self.tmpFile) + " diff: " + repr(self.differenceCache))

    def setStandardFile(self, standardFile):
        self.stdFile = standardFile
        self.stdCmpFile = self.stdFile
        self.diag.info("Setting standard file for " + self.stem + " to " + repr(standardFile))
        
    def recompute(self, test):
        self.freeTextBody = None
        if self.needsRecalculation():
            self.recalculationTime = time.time()
        if self.tmpFile and os.path.isfile(self.tmpFile):
            self.cacheDifferences(test, False)

    def __getstate__(self):
        # don't pickle the diagnostics
        state = {}
        for var, value in self.__dict__.items():
            if var != "diag" and var != "recalculationTime":
                state[var] = value
        return state

    def __setstate__(self, state):
        self.__dict__ = state
        self.diag = logging.getLogger("TestComparison")
        self.recalculationTime = None
        
    def __repr__(self):
        return self.stem
    
    def modifiedDates(self):
        files = [ self.stdFile, self.tmpFile, self.stdCmpFile, self.tmpCmpFile ]
        return " : ".join(map(self.modifiedDate, files))

    def modifiedDate(self, file):
        if not file:
            return "---"
        modTime = plugins.modifiedTime(file)
        if modTime:
            return time.strftime("%d%b%H:%M:%S", time.localtime(modTime))
        else:
            return "---"

    def needsRecalculation(self):
        if not self.stdFile or not self.tmpFile:
            self.diag.info("No comparison, no recalculation")
            return False

        # A test that has been saved doesn't need recalculating
        if self.differenceCache == self.SAVED:
            self.diag.info("Saved file, no recalculation")
            return False

        stdModTime = plugins.modifiedTime(self.stdFile)
        if self.recalculationTime:
            self.diag.info("Already recalculated, checking if file updated since then : " + self.stdFile)
            # If we're already recalculated, only do it again if standard file changes since then
            return stdModTime > self.recalculationTime
        
        tmpModTime = plugins.modifiedTime(self.tmpFile)
        if stdModTime is not None and tmpModTime is not None and stdModTime >= tmpModTime:
            self.diag.info("Standard result newer than generated result at " + self.stdFile)
            return True

        if self.stdFile == self.stdCmpFile: # no filters
            return False
        
        stdCmpModTime = plugins.modifiedTime(self.stdCmpFile)
        self.diag.info("Comparing timestamps for standard files")
        return stdCmpModTime is not None and stdModTime is not None and stdModTime >= stdCmpModTime
    def getType(self):
        return "failure"
    def getDisplayFileName(self):
        if self.newResult():
            return self.tmpFile
        else:
            return self.stdFile
    def getDetails(self):
        # Nothing to report above what is already known
        return ""
    def newResult(self):
        return not self.stdFile and self.tmpFile
    def missingResult(self):
        return self.stdFile and not self.tmpFile
    def isDefunct(self):
        return not self.stdFile and not self.tmpFile
    def hasSucceeded(self):
        return self.stdFile and self.tmpFile and not self.hasDifferences()
    def hasDifferences(self):
        return self.differenceCache == self.DIFFERENT
    
    def getStdFile(self, filtered, postfix=""):
        if filtered:
            return self.stdCmpFile + postfix
        else:
            return self.stdFile + postfix

    def getTmpFile(self, filtered, postfix=""):
        if filtered:
            return self.tmpCmpFile + postfix
        else:
            return self.tmpFile + postfix

    def existingFile(self, *args):
        if self.missingResult() or self.differenceCache == self.SAVED:
            return self.getStdFile(*args)
        else:
            return self.getTmpFile(*args)
        
    def cacheDifferences(self, test, testInProgress):
        filterFileBase = test.makeTmpFileName(self.stem + "." + test.app.name, forFramework=1)
        origCmp = filterFileBase + "origcmp"
        if os.path.isfile(origCmp):
            self.stdCmpFile = origCmp
        tmpCmpFileName = filterFileBase + "cmp"
        if testInProgress:
            tmpCmpFileName = filterFileBase + "partcmp"
        if os.path.isfile(tmpCmpFileName):
            self.tmpCmpFile = tmpCmpFileName

        if self.stdCmpFile and self.tmpCmpFile:
            if filecmp.cmp(self.stdCmpFile, self.tmpCmpFile, 0):
                if self.differenceCache != self.SAVED:
                    self.differenceCache = self.SAME
            else:
                self.differenceCache = self.DIFFERENT
            self.diag.info("Caching differences " + repr(self.stdCmpFile) + " " + repr(self.tmpCmpFile) + " = " + repr(self.differenceCache))

    def getSummary(self, includeNumbers=True):
        if self.newResult():
            return self.stem + " new"
        elif self.missingResult():
            return self.stem + " missing"
        else:
            return self.getDifferencesSummary(includeNumbers)
    def getDifferencesSummary(self, includeNumbers=True):
        return self.stem + " different"
    def getFreeText(self):
        return self.getFreeTextTitle() + "\n" + self.getFreeTextBody()
    def getFreeTextTitle(self):
        if self.missingResult():
            titleText = "Missing result in"
        elif self.newResult():
            titleText = "New result in"
        else:
            titleText = "Differences in"
        titleText += " " + repr(self)
        return "-" * 10 + " " + titleText + " " + "-" * 10
    def getFreeTextBody(self):
        if self.freeTextBody is None:
            self.freeTextBody = self._getFreeTextBody()
        return self.freeTextBody
    def _getFreeTextBody(self):
        if self.binaryFile and \
               (self.newResult() or self.missingResult()):
            message = "Binary file, not showing any preview. " + \
                      "Edit the configuration entry 'binary_file' and re-run if you suspect that this file contains only text.\n"
            return self.previewGenerator.getWrappedLine(message)
        elif self.newResult():
            return self.previewGenerator.getPreview(open(self.tmpCmpFile))
        elif self.missingResult():
            return self.previewGenerator.getPreview(open(self.stdCmpFile))

        try:
            stdFileSize = os.path.getsize(self.stdCmpFile)
            tmpFileSize = os.path.getsize(self.tmpCmpFile)
            if self.textDiffToolMaxSize >= 0 and \
                   (stdFileSize > self.textDiffToolMaxSize or \
                    tmpFileSize > self.textDiffToolMaxSize):
                message = "The result files were too large to compare - " + str(stdFileSize) + " and " + \
                          str(tmpFileSize) + " bytes, compared to the limit of " + str(self.textDiffToolMaxSize) + \
                          " bytes. Adjust the configuration entry 'max_file_size' for the tool '" + self.textDiffTool + \
                          "' and re-run to see the difference in this text view.\n"
                return self.previewGenerator.getWrappedLine(message)

            cmdArgs = plugins.splitcmd(self.textDiffTool) + [ self.stdCmpFile, self.tmpCmpFile ]
            proc = subprocess.Popen(cmdArgs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            return self.previewGenerator.getPreview(proc.stdout)
        except OSError, e:
            self.diag.info("No diff report: full exception printout\n" + plugins.getExceptionString())
            return "No difference report could be created: could not find textual difference tool '" + self.textDiffTool + "'\n" + \
                   "(" + str(e) + ")"
    def updateAfterLoad(self, changedPaths):
        for oldPath, newPath in changedPaths:
            if self.stdFile:
                self.stdFile = self.stdFile.replace(oldPath, newPath)
                self.stdCmpFile = self.stdCmpFile.replace(oldPath, newPath)
            if self.tmpFile:
                self.tmpCmpFile = self.tmpCmpFile.replace(oldPath, newPath)
                self.tmpFile = self.tmpFile.replace(oldPath, newPath)
                
    def versionise(self, fileName, versionString):
        if versionString:
            return fileName + "." + versionString
        else:
            return fileName

    def getStdRootVersionFile(self):
        # drop version identifiers
        dirname, local = os.path.split(self.stdFile)
        localRoot = ".".join(local.split(".")[:2])
        return os.path.join(dirname, localRoot)

    def versionMatchesStd(self, versionString):
        if versionString is None:
            return True
        versions = set(versionString.split("."))
        local = os.path.basename(self.stdFile)
        localVersions = set(local.split(".")[2:])
        return versions == localVersions

    def getStdFileForSave(self, versionString):
        if self.versionMatchesStd(versionString):
            return self.stdFile
        else:
            stdRoot = self.getStdRootVersionFile()
            return self.versionise(stdRoot, versionString)

    def backupOrRemove(self, fileName, backupVersionStrings):
        if os.path.isfile(fileName):
            for backupVersionString in backupVersionStrings:
                backupFile = self.getStdFileForSave(backupVersionString)
                if not os.path.isfile(backupFile):
                    copyfile(fileName, backupFile)
            os.remove(fileName)

    def overwrite(self, test, exact, versionString, backupVersionStrings):
        self.diag.info("save file from " + self.tmpFile)
        self.stdFile = self.getStdFileForSave(versionString)
        self.backupOrRemove(self.stdFile, backupVersionStrings)
        self.saveTmpFile(test, exact)
        
    def saveNew(self, test, versionString):
        self.stdFile = os.path.join(test.getDirectory(), self.versionise(self.stem + "." + test.app.name, versionString))
        self.saveTmpFile(test)

    def getTmpFileForSave(self, test):
        if not test.configValueMatches("save_filtered_file_stems", self.stem):
            return self.tmpFile

        # Don't include the sorting when saving filtered files...
        normalFile = self.tmpCmpFile + ".normal"
        if os.path.isfile(normalFile):
            return normalFile
        else:
            return self.tmpCmpFile

    def saveTmpFile(self, test, exact=True):
        self.diag.info("Saving tmp file to " + self.stdFile)
        plugins.ensureDirExistsForFile(self.stdFile)
        # Allow for subclasses to differentiate between a literal overwrite and a
        # more intelligent save, e.g. for performance. Default is the same for exact
        # and inexact save
        tmpFile = self.getTmpFileForSave(test)
        if os.path.isfile(tmpFile):
            if exact:
                copyfile(tmpFile, self.stdFile)
            else:
                self.saveResults(tmpFile, self.stdFile)
        else:
            raise plugins.TextTestError, "The following file seems to have been removed since it was created:\n" + repr(tmpFile) 
        self.differenceCache = self.SAVED

    def saveMissing(self, versionString, autoGenText, backupVersionStrings):
        stdRoot = self.getStdRootVersionFile()
        self.diag.info("Saving missing file for " + stdRoot + " with version " + repr(versionString))
        targetFile = self.versionise(stdRoot, versionString)
        self.backupOrRemove(targetFile, backupVersionStrings)

        if self.stdFile != targetFile and os.path.isfile(self.stdFile):
            # Create a "versioned-missing" file
            newFile = open(targetFile, "w")
            newFile.write(autoGenText)
            newFile.close()
        self.stdFile = None
        self.stdCmpFile = None
        
    def saveResults(self, tmpFile, destFile):
        copyfile(tmpFile, destFile)
        
