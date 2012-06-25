

import gtk, gobject, entrycompletion, plugins, os, subprocess, types, logging
from guiutils import guiConfig, SubGUI, GUIConfig
from jobprocess import killSubProcessAndChildren
from ordereddict import OrderedDict
        
# The purpose of this class is to provide a means to monitor externally
# started process, so that (a) code can be called when they exit, and (b)
# they can be terminated when TextTest is terminated.
class ProcessTerminationMonitor(plugins.Observable):
    def __init__(self):
        plugins.Observable.__init__(self)
        self.processesForKill = OrderedDict()
        self.exitHandlers = OrderedDict()

    def listRunningProcesses(self):
        processesToCheck = guiConfig.getCompositeValue("query_kill_processes", "", modeDependent=True)
        if "all" in processesToCheck:
            processesToCheck = [ ".*" ]
        if len(processesToCheck) == 0:
            return []
        
        running = []
        triggerGroup = plugins.TextTriggerGroup(processesToCheck)
        for process, description in self.processesForKill.values():
            if triggerGroup.stringContainsText(description):
                running.append("PID " + str(process.pid) + " : " + description)
                
        return running

    def getProcessIdentifier(self, process):
        # Unfortunately the child_watch_add method needs different ways to
        # identify the process on different platforms...
        if os.name == "posix":
            return process.pid
        else:
            return process._handle

    def startProcess(self, cmdArgs, description = "", killOnTermination=True, exitHandler=None, exitHandlerArgs=(), **kwargs):
        process = subprocess.Popen(cmdArgs, stdin=open(os.devnull), **kwargs)
        pidOrHandle = self.getProcessIdentifier(process)
        self.exitHandlers[int(pidOrHandle)] = (exitHandler, exitHandlerArgs)
        if killOnTermination:
            self.processesForKill[int(pidOrHandle)] = (process, description)
        gobject.child_watch_add(pidOrHandle, self.processExited)

    def processExited(self, pid, *args):
        if self.processesForKill.has_key(pid):
            del self.processesForKill[pid]
            
        if self.exitHandlers.has_key(pid):
            exitHandler, exitHandlerArgs = self.exitHandlers.pop(pid)
            if exitHandler:
                exitHandler(*exitHandlerArgs)
    
    def notifyKillProcesses(self, sig=None):
        # Don't leak processes
        if len(self.processesForKill) == 0:
            return
        diag = logging.getLogger("kill processes")
        self.notify("Status", "Terminating all external viewers ...")
        for pid, (process, description) in self.processesForKill.items():
            if self.exitHandlers.has_key(pid):
                self.exitHandlers.pop(pid) # don't call exit handlers in this case, we're terminating
            self.notify("ActionProgress")
            diag.info("Killing '" + description + "' interactive process")
            killSubProcessAndChildren(process, sig)
        
processMonitor = ProcessTerminationMonitor()


class GtkActionWrapper:
    def __init__(self):
        self.accelerator = None
        self.diag = logging.getLogger("Interactive Actions")
        title = self.getTitle(includeMnemonics=True)
        actionName = self.getActionName()
        self.gtkAction = gtk.Action(actionName, title, \
                                    self.getTooltip(), self.getStockId())
        self.gtkAction.connect("activate", self.runInteractive)
        if not self.isActiveOnCurrent():
            self.gtkAction.set_property("sensitive", False)

    def getActionName(self):
        return self.getTitle(includeMnemonics=False)

    def getAccelerator(self, title):
        realAcc = guiConfig.getCompositeValue("gui_accelerators", title)
        if realAcc:
            key, mod = gtk.accelerator_parse(realAcc)
            if gtk.accelerator_valid(key, mod):
                return realAcc
            else:
                plugins.printWarning("Keyboard accelerator '" + realAcc + "' for action '" \
                                     + title + "' is not valid, ignoring ...")

    def addToGroups(self, actionGroup, accelGroup):
        self.accelerator = self._addToGroups(self.gtkAction.get_name().rstrip("."), self.gtkAction, actionGroup, accelGroup)

    def _addToGroups(self, actionName, gtkAction, actionGroup, accelGroup):
        # GTK 2.12 got fussy about this...
        existingAction = actionGroup.get_action(actionName)
        if existingAction:
            self.diag.info("Removing action with label " + existingAction.get_property("label"))
            actionGroup.remove_action(existingAction)
            
        accelerator = self.getAccelerator(actionName)
        actionGroup.add_action_with_accel(gtkAction, accelerator)
        gtkAction.set_accel_group(accelGroup)
        gtkAction.connect_accelerator()
        return accelerator
    
    def setSensitivity(self, newValue):
        self._setSensitivity(self.gtkAction, newValue)

    def _setSensitivity(self, gtkAction, newValue):
        oldValue = gtkAction.get_property("sensitive")
        if oldValue != newValue:
            gtkAction.set_property("sensitive", newValue)



# Introduce an extra level without all the selection-dependent stuff, some actions want
# to inherit from here and it provides a separation
class BasicActionGUI(SubGUI,GtkActionWrapper):
    busy = False
    def __init__(self, *args):
        SubGUI.__init__(self)
        GtkActionWrapper.__init__(self)
        self.topWindow = None

    def checkValid(self, app):
        pass
    
    def notifyTopWindow(self, window):
        self.topWindow = window

    def getParentWindow(self):
        return self.topWindow

    def isModal(self):
        return True

    def isActiveOnCurrent(self, *args):
        return True
    
    def getDialogTitle(self):
        return self.getTooltip()

    def createDialog(self):
        if self.isModal():
            dialog = gtk.Dialog(self.getDialogTitle(), self.getParentWindow(), flags=gtk.DIALOG_MODAL) 
            dialog.set_modal(True)
        else:
            dialog = gtk.Dialog(self.getDialogTitle())

        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        return dialog
    
    def getTitle(self, includeMnemonics=False):
        title = self._getTitle()
        if includeMnemonics:
            return title
        else:
            return title.replace("_", "")

    def getTooltip(self):
        return self.getTitle(includeMnemonics=False)

    def displayInTab(self):
        return False

    def allAppsValid(self):
        return True
    
    def getStockId(self):
        stockId = self._getStockId()
        if stockId:
            return "gtk-" + stockId 

    def _getStockId(self): # The stock ID for the action, in toolbar and menu.
        pass
                
    def setObservers(self, observers):
        signals = [ "Status", "ActionProgress" ] + self.getSignalsSent()
        self.diag.info("Observing " + str(self.__class__) + " :")
        for observer in observers:
            for signal in signals:
                if hasattr(observer, "notify" + signal):
                    self.diag.info("-> " + str(observer.__class__))
                    self.addObserver(observer)
                    break
    def getSignalsSent(self):
        return [] # set up like this so every single derived class doesn't have to include it

    def createDialogMessage(self, message, stockIcon):
        buffer = gtk.TextBuffer()
        buffer.set_text(message)
        textView = gtk.TextView(buffer)
        textView.set_editable(False)
        textView.set_cursor_visible(False)
        textView.set_left_margin(5)
        textView.set_right_margin(5)
        hbox = gtk.HBox()
        imageBox = gtk.VBox()
        imageBox.pack_start(gtk.image_new_from_stock(stockIcon, gtk.ICON_SIZE_DIALOG), expand=False)
        hbox.pack_start(imageBox, expand=False)
        scrolledWindow = gtk.ScrolledWindow()
        # What we would like is that the dialog expands without scrollbars
        # until it reaches some maximum size, and then adds scrollbars. At
        # the moment I cannot make this happen without setting a fixed window
        # size, so I'll set the scrollbar policy to never instead.
        scrolledWindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_NEVER)
        scrolledWindow.add(textView)
        scrolledWindow.set_shadow_type(gtk.SHADOW_IN)
        hbox.pack_start(scrolledWindow, expand=True, fill=True)
        alignment = gtk.Alignment()
        alignment.set_padding(5, 5, 0, 5)
        alignment.add(hbox)
        return alignment
            
    def showErrorDialog(self, message):
        self.showErrorWarningDialog(message, gtk.STOCK_DIALOG_ERROR, "Error") 
    def showWarningDialog(self, message):
        self.showErrorWarningDialog(message, gtk.STOCK_DIALOG_WARNING, "Warning") 
    def showErrorWarningDialog(self, message, stockIcon, alarmLevel):
        dialog = self.createAlarmDialog(self.getParentWindow(), message, stockIcon, alarmLevel)
        dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        dialog.connect("response", lambda d, r: self._cleanDialog(d))
        dialog.show_all()
        
    def createAlarmDialog(self, parent, message, stockIcon, alarmLevel):
        dialogTitle = "TextTest " + alarmLevel
        dialog = gtk.Dialog(dialogTitle, parent, flags=gtk.DIALOG_MODAL) 
        dialog.set_modal(True)
        
        contents = self.createDialogMessage(message, stockIcon)
        dialog.vbox.pack_start(contents, expand=True, fill=True)
        return dialog
    
    def showQueryDialog(self, parent, message, stockIcon, alarmLevel, respondMethod, respondData=None):
        dialog = self.createAlarmDialog(parent, message, stockIcon, alarmLevel)
        dialog.set_default_response(gtk.RESPONSE_NO)
        dialog.add_button(gtk.STOCK_NO, gtk.RESPONSE_NO)
        dialog.add_button(gtk.STOCK_YES, gtk.RESPONSE_YES)
        dialog.connect("response", respondMethod, respondData)
        dialog.show_all()
        
    def _cleanDialog(self, dialog, *args):
        entrycompletion.manager.collectCompletions()
        dialog.hide() # Can't destroy it, we might still want to read stuff from it
        
    def respond(self, dialog, responseId, *args):
        saidOK = responseId in [ gtk.RESPONSE_ACCEPT, gtk.RESPONSE_YES, gtk.RESPONSE_OK ]
        try:
            self._respond(saidOK, dialog, *args)
        except plugins.TextTestError, e:
            self.showErrorDialog(str(e))
            
    def _respond(self, saidOK, dialog, *args):
        if saidOK:
            self._runInteractive()
        else:
            self.cancel()
        if dialog:
            self._cleanDialog(dialog, *args)
        
    def getConfirmationMessage(self):
        return ""

    def runInteractive(self, *args):
        if self.busy: # If we're busy with some other action, ignore this one ...
            return
                
        try:
            confirmationMessage = self.getConfirmationMessage()
            if confirmationMessage:
                self.showQueryDialog(self.getParentWindow(), confirmationMessage,
                                     gtk.STOCK_DIALOG_WARNING, "Confirmation", self.respond)    
            else:
                # Each time we perform an action we collect and save the current registered entries
                # Actions showing dialogs will handle this in the dialog code.
                entrycompletion.manager.collectCompletions()
                self._runInteractive()
        except plugins.TextTestError, e:
            self.showErrorDialog(str(e))
            
    def _runInteractive(self):
        try:
            BasicActionGUI.busy = True
            self.startPerform()
        finally:
            self.endPerform()
            BasicActionGUI.busy = False
    
    def messageBeforePerform(self):
        # Don't change this by default, most of these things don't take very long
        pass

    def messageAfterPerform(self):
        return "Performed '" + self.getTooltip() + "'."
    
    def startPerform(self):
        message = self.messageBeforePerform()
        if message != None:
            self.notify("Status", message)
        self.notify("ActionStart")
        self.notify("ActionProgress")
        self.performOnCurrent()
        message = self.messageAfterPerform()
        if message != None:
            self.notify("Status", message)
        
    def endPerform(self):
        self.notify("ActionStop")

    def cancel(self):
        self.notify("Status", "Action cancelled.")
    
    
class ActionGUI(BasicActionGUI):
    busy = False
    def __init__(self, allApps, *args):
        self.currTestSelection = []
        self.currFileSelection = []
        self.currAppSelection = []
        self.validApps = []
        self.noApps = len(allApps) == 0
        BasicActionGUI.__init__(self)
        for app in allApps:
            self._checkAllValid(app)
    
    def checkValid(self, app):
        self._checkValid(app)
        self.noApps = False

    def _checkAllValid(self, app):
        for currApp in [ app ] + app.extras:
            if currApp not in self.validApps:
                self._checkValid(currApp)
                        
    def _checkValid(self, app):
        if self.isValidForApp(app):
            self.validApps.append(app)
        else:
            self.diag.info(str(self.__class__) + " invalid for " + repr(app))
        
    def isValidForApp(self, dummyApp):
        return True

    def shouldShow(self):
        return self.noApps or len(self.validApps) > 0
    
    def notifyNewTestSelection(self, *args):
        newActive = self.updateSelection(*args)
        self.setSensitivity(newActive)

    def getTestCaseSelection(self):
        testcases = []
        for test in self.currTestSelection:
            for testCase in test.testCaseList():
                if not testCase in testcases:
                    testcases.append(testCase)
        return testcases

    def updateSelection(self, tests, apps, rowCount, *args):
        if rowCount != 1 and self.singleTestOnly():
            self.currTestSelection = []
        else:
            self.currTestSelection = tests
            testClass = self.correctTestClass()
            if testClass:
                self.currTestSelection = filter(lambda test: test.classId() == testClass, tests)
                
        self.currAppSelection = apps
        newActive = self.allAppsValid() and self.isActiveOnCurrent()
        self.diag.info("New test selection for " + self.getTitle() + "=" + repr(tests) + " : new active = " + repr(newActive))
        return newActive
        
    def notifyLifecycleChange(self, test, state, *args):
        newActive = self.isActiveOnCurrent(test, state)
        self.setSensitivity(newActive)

    def notifyNewFileSelection(self, files):
        newActive = self.updateFileSelection(files)
        self.setSensitivity(newActive)
        
    def updateFileSelection(self, files):
        self.currFileSelection = files
        newActive = self.allAppsValid() and self.isActiveOnCurrent()
        self.diag.info("New file selection for " + self.getTitle() + "=" + repr(files) + " : new active = " + repr(newActive))
        return newActive

    def allAppsValid(self):
        for app in self.currAppSelection:
            if app not in self.validApps:
                self.diag.info("Rejecting due to invalid selected app : " + repr(app))
                return False
        return True

    def isActiveOnCurrent(self, *args):
        return self.shouldShow() and len(self.currTestSelection) > 0
        
    def singleTestOnly(self):
        return False        

    def describeTests(self):
        if len(self.currTestSelection) == 1:
            return "test " + self.currTestSelection[0].getRelPath()
        else:
            return str(len(self.currTestSelection)) + " tests"

    def correctTestClass(self):
        pass

    def messageAfterPerform(self):
        return "Performed '" + self.getTooltip() + "' on " + self.describeTests() + "."

    def createButton(self):
        button = gtk.Button()
        self.gtkAction.connect_proxy(button)
        # In theory all this should be automatic, but it appears not to work
        if self.getStockId():
            button.set_image(gtk.image_new_from_stock(self.getStockId(), gtk.ICON_SIZE_BUTTON))
        button.set_tooltip_text(self.getTooltip())
        button.show()
        return button
    

# These actions consist of bringing up a dialog and only doing that
# (i.e. the dialog is not a mechanism to steer how the action should be run)
class ActionResultDialogGUI(ActionGUI):
    def __init__(self, *args, **kw):
        self.dialog = None
        ActionGUI.__init__(self, *args, **kw)
        
    def performOnCurrent(self):
        self.dialog = self.createDialog()
        self.addContents()
        self.createButtons()
        self.dialog.show_all()
        
    def addContents(self): # pragma: no cover - documentation only
        pass
    
    def createButtons(self):
        self.dialog.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_ACCEPT)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        self.dialog.connect("response", self.respond)

    def respond(self, dialog, responseId):
        if responseId != gtk.RESPONSE_NONE:
            self._cleanDialog(dialog)

class ComboBoxListFinder:
    def __init__(self, combobox):
        self.model = combobox.get_model()
        self.textColumn = combobox.get_text_column()
    def __call__(self):
        entries = []
        self.model.foreach(self.getText, entries)
        return entries
    def getText(self, model, dummyPath, iter, entries):
        text = model.get_value(iter, self.textColumn)
        entries.append(text)


# A utility class to set and get the indices of options in radio button groups.
class RadioGroupIndexer:
    def __init__(self, listOfButtons):
        self.buttons = listOfButtons

    def getActiveIndex(self):
        for i in xrange(0, len(self.buttons)):
            if self.buttons[i].get_active():
                return i

    def setActiveIndex(self, index):
        self.buttons[index].set_active(True)


class OptionGroupGUI(ActionGUI):
    def __init__(self, *args):
        ActionGUI.__init__(self, *args)
        self.groupBoxes = {}
        self.optionGroup = plugins.OptionGroup(self.getTabTitle())
        # convenience shortcuts...
        self.addOption = self.optionGroup.addOption
        self.addSwitch = self.optionGroup.addSwitch
        
    def updateOptions(self):
        return False     

    def updateForConfig(self, option):
        fromConfig = guiConfig.getCompositeValue("gui_entry_overrides", option.name)
        # only do this if it hasn't previously been manually overwritten
        if fromConfig is not None and fromConfig != "<not set>" and option.getValue() == option.defaultValue:
            option.setValue(fromConfig)
            return fromConfig

    def createLabelEventBox(self, option, separator):
        label = gtk.EventBox()
        label.add(gtk.Label(option.name + separator))
        if option.description and type(option.description) == types.StringType:
            label.set_tooltip_text(option.description)
        return label

    def connectEntry(self, option, entryOrBuffer):
        entryOrBuffer.set_text(str(option.getValue()))
        # Don't pass entry.set_text directly, it will mess up StoryText's programmatic method interception
        option.setMethods(self.getGetTextMethod(entryOrBuffer), lambda t: entryOrBuffer.set_text(str(t)))
        if option.changeMethod:
            entryOrBuffer.connect("changed", option.changeMethod)
        
    def getGetTextMethod(self, widget):
        if isinstance(widget, gtk.SpinButton):
            # Would be nice to return widget.get_value_as_int but that returns the wrong answer from
            # dialogs that have been closed
            def get_text():
                return int(widget.get_text())
            return get_text
        elif isinstance(widget, gtk.Entry):
            return widget.get_text
        else:
            def get_text():
                return widget.get_text(widget.get_start_iter(), widget.get_end_iter())
            return get_text

    def addValuesFromConfig(self, option, includeOverrides=True):
        if includeOverrides:
            newValue = self.updateForConfig(option)
            if newValue:
                option.addPossibleValue(newValue)
        for extraOption in self.getConfigOptions(option):
            option.addPossibleValue(extraOption)

    def createRadioButtonCollection(self, switch, optionGroup):
        hbox = gtk.HBox()
        if len(switch.name) > 0:
            label = self.createLabelEventBox(switch, ":")
            hbox.pack_start(label, expand=False, fill=False)
        for button in self.createRadioButtons(switch, optionGroup):
            hbox.pack_start(button, expand=True, fill=False)
        hbox.show_all()
        return hbox

    def setConfigOverride(self, switch, index, option, *args):
        configName = self.getNaming(switch.name, option, *args)
        if index == switch.getValue() or guiConfig.getCompositeValue("gui_entry_overrides", configName) == "1":
            switch.setValue(index)

    def getNaming(self, switchName, option, *args):
        if len(switchName) > 0:
            return switchName + ":" + option
        else:
            return option

    def createRadioButtons(self, switch, optionGroup):
        buttons = []
        mainRadioButton = None
        individualToolTips = type(switch.description) == types.ListType
        for index, option in enumerate(switch.options):
            self.setConfigOverride(switch, index, option, optionGroup)
            radioButton = gtk.RadioButton(mainRadioButton, option, use_underline=True)
            self.setRadioButtonName(radioButton, option, optionGroup)
            if individualToolTips:
                radioButton.set_tooltip_text(switch.description[index])
                
            buttons.append(radioButton)
            if not mainRadioButton:
                mainRadioButton = radioButton
            if switch.getValue() == index:
                radioButton.set_active(True)
            else:
                radioButton.set_active(False)

        indexer = RadioGroupIndexer(buttons)
        switch.setMethods(indexer.getActiveIndex, indexer.setActiveIndex)
        return buttons

    def createFrame(self, group, name):
        frame = gtk.Frame(name)
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(gtk.SHADOW_IN)
        frame.add(self.createGroupBox(group))
        return frame

    def createGroupBox(self, group):
        frameBox = gtk.VBox()
        frameBox.set_border_width(10)
        self.fillVBox(frameBox, group)
        self.groupBoxes[group] = frameBox
        return frameBox

    def setGroupSensitivity(self, group, *args, **kw):
        widget = self.groupBoxes.get(group)
        self.setChildSensitivity(widget, *args, **kw)

    def setChildSensitivity(self, widget, sensitive, ignoreWidget=None):
        if widget is ignoreWidget or isinstance(widget, gtk.RadioButton):
            return
        elif isinstance(widget, (gtk.Entry, gtk.CheckButton, gtk.ComboBoxEntry)):
            widget.set_sensitive(sensitive)
        elif hasattr(widget, "get_children"):
            for child in widget.get_children():
                self.setChildSensitivity(child, sensitive, ignoreWidget)

    def setRadioButtonName(self, *args):
        pass # Don't bother by default, it's easy to set stupid names...

    def createComboBox(self, switch, *args):
        combobox = gtk.combo_box_new_text()
        combobox.set_name(switch.name)
        for index, option in enumerate(switch.options):
            combobox.append_text(option)
            self.setConfigOverride(switch, index, option, *args)
            if switch.getValue() == index:
                combobox.set_active(index)

        switch.setMethods(combobox.get_active, combobox.set_active)
        box = gtk.VBox()
        box.pack_start(gtk.Label(""))
        box.pack_start(combobox)
        return box

    def createSwitchWidget(self, switch, optionGroup):
        if len(switch.options) >= 1:
            if switch.hideOptions:
                return self.createComboBox(switch, optionGroup)
            else:
                return self.createRadioButtonCollection(switch, optionGroup)
        else:
            return self.createCheckBox(switch)

    def createCheckBox(self, switch):
        self.updateForConfig(switch)
        checkButton = gtk.CheckButton(switch.name)
        if switch.description:
            checkButton.set_tooltip_text(switch.description)
        
        if int(switch.getValue()):
            checkButton.set_active(True)
        # Don't pass checkButton.set_active as that will screw up StoryText's interception of it
        switch.setMethods(checkButton.get_active, lambda x: checkButton.set_active(x))
        checkButton.show()
        return checkButton

    def createComboBoxEntry(self, option):
        combobox = gtk.combo_box_entry_new_text()
        entry = combobox.child
        combobox.set_row_separator_func(self.isRowSeparator)
        option.setPossibleValuesMethods(combobox.append_text, ComboBoxListFinder(combobox))
        
        option.setClearMethod(combobox.get_model().clear)
        return combobox, entry

    def isRowSeparator(self, model, iter):
        text = model.get_value(iter, 0)
        return text == "-" * 10

    def createOptionWidget(self, option):
        optionName = option.name.strip()
        if option.multilineEntry:
            frame = gtk.Frame()
            frame.set_shadow_type(gtk.SHADOW_OUT)
            frame.set_border_width(1)
            view = gtk.TextView()
            view.set_name(optionName)
            frame.add(view)
            return frame, view.get_buffer()
        else:
            box = gtk.HBox()
            if option.usePossibleValues():
                widget, entry = self.createComboBoxEntry(option)
                widget.set_name(optionName + " (Combo Box)")
                box.pack_start(widget, expand=True, fill=True)
            else:
                value = option.getValue()
                if isinstance(value, int):
                    adjustment = gtk.Adjustment(value=value, lower=self.getLowerBoundForSpinButtons(),
                                                upper=1000, step_incr=1)
                    entry = gtk.SpinButton(adjustment)
                    entry.set_numeric(True)
                else:
                    entry = gtk.Entry()
                box.pack_start(entry, expand=True, fill=True)

            entry.set_name(optionName)
            entrycompletion.manager.register(entry)
            # Options in drop-down lists don't change, so we just add them once and for all.
            for text in option.listPossibleValues():
                entrycompletion.manager.addTextCompletion(text)

            return box, entry

    def getLowerBoundForSpinButtons(self):
        return 0

    def createFileChooserDialog(self, box, entry, option):
        button = gtk.Button("...")
        box.pack_start(button, expand=False, fill=False)
        button.connect("clicked", self.showFileChooser, entry, option)
        
    def showFileChooser(self, dummyWidget, entry, option):
        dialog = gtk.FileChooserDialog("Select a file",
                                       self.getParentWindow(),
                                       gtk.FILE_CHOOSER_ACTION_OPEN,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,                                        
                                        gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        self.startFileChooser(dialog, entry, option)
    
    def startFileChooser(self, dialog, entry, option):
        # Folders is a list of pairs (short name, absolute path),
        # where 'short name' means the name given in the config file, e.g.
        # 'temporary_filter_files' or 'filter_files' ...
        dialog.set_modal(True)
        folders, defaultFolder = option.getDirectories()
        dialog.connect("response", self.respondFileChooser, entry)
        # If current entry forms a valid path, set that as default
        currPath = entry.get_text()
        currDir = os.path.split(currPath)[0]
        if os.path.isdir(currDir):
            dialog.set_current_folder(currDir)
        elif defaultFolder and os.path.isdir(os.path.abspath(defaultFolder)):
            dialog.set_current_folder(os.path.abspath(defaultFolder))
        for folder in folders:
            dialog.add_shortcut_folder(folder)
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.show()
        
    def respondFileChooser(self, dialog, response, entry):
        if response == gtk.RESPONSE_OK:
            entry.set_text(dialog.get_filename().replace("\\", "/"))
            entry.set_position(-1) # Sets position last, makes it possible to see the vital part of long paths 
        dialog.destroy()
  
    def getConfigOptions(self, option):
        fromConfig = guiConfig.getCompositeValue("gui_entry_options", option.name)
        if fromConfig is None: #Happens on initial startup with no apps...
            return []
        return fromConfig

    def getCommandLineArgs(self, optionGroup, onlyKeys=[]):
        args = []
        for key, value in optionGroup.getOptionsForCmdLine(onlyKeys):
            args.append("-" + key)
            if value:
                args.append(str(value))
        return args

    def hasPerformance(self, apps, *args):
        for app in apps:
            if app.hasPerformance(*args):
                return True
        return False

    def addApplicationOptions(self, allApps, optionGroup, inputOptions={}):
        if len(allApps) > 0:
            for app in allApps:
                app.addToOptionGroups(allApps, [ optionGroup ])
        else:
            configObject = self.makeDefaultConfigObject(inputOptions)
            configObject.addToOptionGroups(allApps, [ optionGroup ])

    def makeDefaultConfigObject(self, inputOptions):
        return plugins.importAndCall("default", "getConfig", inputOptions)


    
class ActionTabGUI(OptionGroupGUI):
    def __init__(self, *args):
        OptionGroupGUI.__init__(self, *args)
        self.diag.info("Creating action tab for " + self.getTabTitle() + ", sensitive " + repr(self.shouldShowCurrent()))
        self.vbox = gtk.VBox()

    def shouldShowCurrent(self, *args):
        return self.gtkAction.get_property("sensitive")

    def createView(self):
        self.fillVBox(self.vbox, self.optionGroup)
        self.createButtons(self.vbox)
        self.vbox.show_all()
        self.widget = self.addScrollBars(self.vbox, hpolicy=gtk.POLICY_AUTOMATIC)
        self.widget.set_name(self.getTabTitle() + " Tab")
        return self.widget

    def setSensitivity(self, newValue):
        ActionGUI.setSensitivity(self, newValue)
        self.diag.info("Sensitivity of " + self.getTabTitle() + " changed to " + repr(newValue))
        if self.shouldShowCurrent():
            self.updateOptions()

    def displayInTab(self):
        return True
    
    def notifyReset(self, *args):
        self.optionGroup.reset()

    def extractSwitches(self, optionGroup):
        options, switches = [], []
        for option in optionGroup.options.values():
            if isinstance(option, plugins.Switch):
                switches.append(option)
            else:
                options.append(option)
        return options, switches
    
    def fillVBox(self, vbox, optionGroup):
        options, switches = self.extractSwitches(optionGroup)
        if len(options) > 0:
            # Creating 0-row table gives a warning ...
            table = gtk.Table(len(options), 2, homogeneous=False)
            table.set_row_spacings(1)
            rowIndex = 0        
            for option in options:
                self.addValuesFromConfig(option)

                labelEventBox = self.createLabelEventBox(option, separator="  ")
                labelEventBox.get_children()[0].set_alignment(1.0, 0.5)
                table.attach(labelEventBox, 0, 1, rowIndex, rowIndex + 1, xoptions=gtk.FILL, xpadding=1)
                entryWidget, entryOrBuffer = self.createOptionWidget(option)
                self.connectEntry(option, entryOrBuffer) 
                if isinstance(entryOrBuffer, gtk.Entry):
                    entryOrBuffer.connect("activate", self.runInteractive)
                table.attach(entryWidget, 1, 2, rowIndex, rowIndex + 1)
                rowIndex += 1
                table.show_all()
            vbox.pack_start(table, expand=False, fill=False)

        for switch in switches:
            widget = self.createSwitchWidget(switch, optionGroup)
            vbox.pack_start(widget, expand=False, fill=False)

    def createResetButton(self):
        button = gtk.Button("Reset Tab")
        button.set_name("Reset " + self.getTabTitle() + " Tab")
        button.connect("clicked", self.notifyReset)
        button.set_tooltip_text("Reset all the settings in the current tab to their default values")
        button.show()
        return button
    
    def createButtons(self, vbox):
        self.addCentralButton(vbox, self.createButton(), padding=8)
        self.addCentralButton(vbox, self.createResetButton(), padding=16)

    def addCentralButton(self, vbox, button, padding):
        buttonbox = gtk.HButtonBox()
        buttonbox.pack_start(button, expand=True, fill=False)
        vbox.pack_start(buttonbox, expand=False, fill=False, padding=padding)

    def createOptionWidget(self, option):
        box, entry = OptionGroupGUI.createOptionWidget(self, option)
        if option.selectFile:
            self.createFileChooserDialog(box, entry, option)
        return (box, entry)

class ActionDialogGUI(OptionGroupGUI):
    def runInteractive(self, *args):
        if self.busy: # If we're busy with some other action, ignore this one ...
            return
                
        try:
            self.showConfigurationDialog()
        except plugins.TextTestError, e:
            self.showErrorDialog(str(e))
            
    def showConfigurationDialog(self):
        dialog = self.createDialog()
        alignment = self.createAlignment()
        vbox = gtk.VBox()
        fileChooser, fileChooserOption = self.fillVBox(vbox, self.optionGroup)
        alignment.add(vbox)
        dialog.vbox.pack_start(alignment, expand=True, fill=True)
        self.createButtons(dialog, fileChooser, fileChooserOption)
        self.tryResize(dialog)
        dialog.show_all()
        
    def getConfirmationDialogSettings(self):
        return gtk.STOCK_DIALOG_WARNING, "Confirmation"
    
    def _respond(self, saidOK=True, dialog=None, fileChooserOption=None):
        if saidOK:
            try:
                message = self.getConfirmationMessage()
                if message:
                    stockId, level = self.getConfirmationDialogSettings()
                    self.showQueryDialog(self.getQueryParentWindow(dialog), message, stockId, level,
                                         self.confirmationRespond, fileChooserOption)
                else:
                    self.defaultRespond(saidOK, dialog, fileChooserOption)
            except plugins.TextTestError, e:
                self.showErrorDialog(str(e))
        else:
            self.defaultRespond(saidOK, dialog, fileChooserOption)

    def getQueryParentWindow(self, dialog):
        if dialog:
            return dialog
        else:
            return self.getParentWindow()

    def confirmationRespond(self, dialog, responseId, fileChooserOption):
        saidOK = responseId == gtk.RESPONSE_YES
        self.defaultRespond(saidOK, dialog)
        if saidOK:
            parent = dialog.get_transient_for()
            if isinstance(parent, gtk.Dialog):
                self._cleanDialog(parent, fileChooserOption)

    def _cleanDialog(self, dialog, fileChooserOption=None):
        if fileChooserOption:
            fileChooserOption.resetDefault() # Must do this, because we can't rely on reading from invisible FileChoosers
        OptionGroupGUI._cleanDialog(self, dialog)
        
    def defaultRespond(self, *args):
        OptionGroupGUI._respond(self, *args)

    def tryResize(self, dialog):
        horfrac, verfrac = self.getSizeAsWindowFraction()
        if horfrac is not None:
            width, height = self.topWindow.get_size()
            dialog.resize(int(width * horfrac), int(height * verfrac))
        
    def getSizeAsWindowFraction(self):
        return None, None
    
    def setSensitivity(self, newValue):
        ActionGUI.setSensitivity(self, newValue)
        if newValue:
            self.updateOptions()
            
    def createAlignment(self):
        alignment = gtk.Alignment()
        alignment.set(1.0, 1.0, 1.0, 1.0)
        alignment.set_padding(5, 5, 5, 5)
        return alignment

    def getOkStock(self, scriptName):
        if scriptName.startswith("load"):
            return "texttest-stock-load"
        elif scriptName.startswith("save"):
            return gtk.STOCK_SAVE
        else:
            return gtk.STOCK_OK

    def createButtons(self, dialog, fileChooser, fileChooserOption):
        dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        actionScriptName = self.getTooltip()
        dialog.add_button(self.getOkStock(actionScriptName.lower()), gtk.RESPONSE_ACCEPT)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        if fileChooser:
            fileChooser.connect("file-activated", self.simulateResponse, dialog)
            # Don't pass set_filename directly, will interfere with StoryText's attempts to intercept it
            fileChooserOption.setMethods(fileChooser.get_filename, lambda f: fileChooser.set_filename(f))
        
        dialog.connect("response", self.respond, fileChooserOption)

    def simulateResponse(self, dummy, dialog):
        dialog.response(gtk.RESPONSE_ACCEPT)
        
    def fillVBox(self, vbox, optionGroup, includeOverrides=True):
        fileChooser, fileChooserOption = None, None
        allOptions = optionGroup.options.values()
        for option in allOptions:
            self.addValuesFromConfig(option, includeOverrides)
            
            if isinstance(option, plugins.Switch):
                widget = self.createSwitchWidget(option, optionGroup)
                vbox.pack_start(widget, expand=False, fill=False)
            elif option.selectFile or option.selectDir or option.saveFile:
                if not self.showFileChooserAsDialog():
                    fileChooserOption = option
                    fileChooser = self.createFileChooser(option)
                    if len(allOptions) > 1 and not option.saveFile:
                        # If there is other stuff, add a frame round the file chooser so we can see what it's for
                        # Don't do this when saving as it shouldn't be necessary
                        labelEventBox = self.createLabelEventBox(option, separator=":")
                        frame = gtk.Frame()
                        frame.set_label_widget(labelEventBox)
                        frame.add(fileChooser)
                        vbox.pack_start(frame, expand=True, fill=True)
                    else:
                        vbox.pack_start(fileChooser, expand=True, fill=True)
                else:
                    widget, entry = self.createOptWidget(vbox, option)
                    self.createFileChooserDialog(widget, entry, option)
            else:
                self.createOptWidget(vbox, option)

        if fileChooser:
            # File choosers seize the focus, mostly we want to get it back and put it on the first text entry
            self.set_focus(vbox)

        return fileChooser, fileChooserOption

    def set_focus(self, vbox):
        for child in vbox.get_children():
            if isinstance(child, gtk.Container):
                for gchild in child.get_children():
                    if isinstance(gchild, gtk.Entry):
                        gchild.get_toplevel().connect("map", lambda x: gchild.grab_focus())
                        return

    def createOptWidget(self, vbox, option):
        labelEventBox = self.createLabelEventBox(option, separator=":")
        self.addLabel(vbox, labelEventBox)
        entryWidget, entryOrBuffer = self.createOptionWidget(option)
        if isinstance(entryOrBuffer, gtk.Entry):
            entryOrBuffer.set_activates_default(True)
            vbox.pack_start(entryWidget, expand=False, fill=False)
        else:
            vbox.pack_start(entryWidget, expand=True, fill=True)
        self.connectEntry(option, entryOrBuffer)
        return entryWidget, entryOrBuffer

    def addLabel(self, vbox, label):
        hbox = gtk.HBox()
        hbox.pack_start(label, expand=False, fill=False)        
        vbox.pack_start(hbox, expand=False, fill=False, padding=2)
                
    def createRadioButtonCollection(self, switch, optionGroup):
        if optionGroup is not self.optionGroup:
            # If we're not part of the main group, we've got a frame already, store horizontally in this case
            return OptionGroupGUI.createRadioButtonCollection(self, switch, optionGroup)

        if switch.name:
            frame = gtk.Frame(switch.name)
        else:
            frame = gtk.Frame()
        frameBox = gtk.VBox()
        for button in self.createRadioButtons(switch, optionGroup):
            frameBox.pack_start(button)
        frame.add(frameBox)
        return frame
    
    def showFileChooserAsDialog(self):
        return False
    
    def getFileChooserFlag(self, option):
        if option.selectFile:
            return gtk.FILE_CHOOSER_ACTION_OPEN
        elif option.selectDir:
            return gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
        else:
            return gtk.FILE_CHOOSER_ACTION_SAVE

    def createFileChooser(self, option):
        fileChooser = gtk.FileChooserWidget(self.getFileChooserFlag(option))
        fileChooser.set_name("File Chooser for '" + self.getTooltip() + "'")
        fileChooser.set_show_hidden(True)
        folders, defaultFolder = option.getDirectories()
        startFolder = os.getcwd() # Just to make sure we always have some dir ...
        if defaultFolder and os.path.isdir(os.path.abspath(defaultFolder)):
            startFolder = os.path.abspath(defaultFolder)
            
        # We want a filechooser dialog to let the user choose where, and
        # with which name, to save the selection.
        fileChooser.set_current_folder(startFolder)
        for folder in folders:
            try:
                fileChooser.add_shortcut_folder(folder)
            except gobject.GError:
                pass # Get this if the folder is already added, e.g. if it's the home directory
        if not option.saveFile and option.getValue():
            fileChooser.set_filename(option.getValue())
            
        fileChooser.set_local_only(True)
        return fileChooser

    def getFilterFileDirs(self, allApps, **kw):
        if len(allApps) > 0:
            return allApps[0].getFilterFileDirectories(allApps, **kw)
        else:
            return []
        

class InteractiveActionConfig:
    def getColourDictionary(self):
        return GUIConfig.getDefaultColours()
        
    def getDefaultAccelerators(self):
        return {}

    def getReplacements(self):
        # Return a dictionary mapping classes above to what to replace them with
        return {}
