#!/usr/local/bin/python

from queuesystem import QueueSystemConfig
import plugins

def getConfig(optionMap):
    return Config(optionMap)

class Config(QueueSystemConfig):
    def getTestRunner(self):
        if self.slaveRun():
            return RunTestInSlave()
        else:
            return QueueSystemConfig.getTestRunner(self)

class RunTestInSlave(plugins.Action):
    def __call__(self, test):
        wibble
