#!/usr/bin/env python

import scriptengine, definitions
import os, sys, logging.config, optparse

def create_option_parser():
    usage = """usage: %prog [options] <program> <program_args> ...

StoryText is a record/replay tool for Python GUIs, currently consisting of a generic 
interface and an implementation for PyGTK. Unlike traditional record/replay tools, 
it does not record UI events directly but relies on its user maintaining a mapping 
between the current UI controls and "domain language" names that express the 
intent of the actions, allowing tests to be recorded in a very high level customer-readable format.

For PyGTK, it also generates a logfile describing in a textual format the visible GUI and the changes
that occur in it. This makes it easy to test PyGTK GUIs using a text-based test tool such as TextTest.
It does not currently have any other means of "asserting" what is happening in the GUI.

For fuller documentation refer to the online docs at http://www.texttest.org"""

    parser = optparse.OptionParser(usage, version="%prog " + definitions.__version__)
    parser.disable_interspersed_args() # don't try to parse the application's args
    parser.add_option("-d", "--delay", metavar="SECONDS", 
                      help="amount of time to wait between each action when replaying. Also enabled via the environment variable USECASE_REPLAY_DELAY.")
    parser.add_option("-i", "--interface", metavar="INTERFACE",
                      help="type of interface used by application, should be 'console', 'gtk' or 'tkinter' ('gtk' is default)", 
                      default="gtk")
    parser.add_option("-l", "--loglevel", default="INFO", 
                      help="produce logging at level LEVEL, should be 'info', 'debug', 'config' or 'off'. 'info' will point the auto-generated GUI log at standard output. 'debug' will produce a large amount of StoryText debug information on standard output. 'off' will disable the auto-generated log. 'config' will enabled the auto-generated log but not set any global log level: it is a way to tell StoryText that your application will configure its logging via its own log configuration files.", metavar="LEVEL")
    parser.add_option("-L", "--logconfigfile",
                      help="Configure StoryText logging via the log configuration file at FILE. A suitable sample file can be find with the source tree under the 'log' directory.", metavar="FILE")
    parser.add_option("-m", "--mapfiles", default=os.path.join(scriptengine.ScriptEngine.storytextHome, "ui_map.conf"),
                      help="Use the UI map file(s) at FILE1,... If not set StoryText will read and write such a file at the location determined by $STORYTEXT_HOME/ui_map.conf. If run standalone $STORYTEXT_HOME defaults to ~/.storytext, while TextTest will point it to a 'storytext_files' subdirectory of the root test suite. If multiple files are provided, the last in the list will be used for writing.", metavar="FILE1,...")
    parser.add_option("-p", "--replay", 
                      help="replay script from FILE. Also enabled via the environment variable USECASE_REPLAY_SCRIPT.", metavar="FILE")
    parser.add_option("-r", "--record", 
                      help="record script to FILE. Also enabled via the environment variable USECASE_RECORD_SCRIPT.", metavar="FILE")
    parser.add_option("-s", "--supported", action="store_true",
                      help="list which PyGTK widgets and signals are currently supported 'out-of-the-box'")
    parser.add_option("--supported-html", action="store_true", help=optparse.SUPPRESS_HELP)
    parser.add_option("-x", "--disable_usecase_names", action="store_true", 
                      help="Disable the entering of usecase names when unrecognised actions are recorded. Recommended only for quick-and-dirty experimenting. Will result in recorded scripts that are easy to make but hard to read and hard to maintain.")
    return parser


def create_script_engine(options, install_root):
    logLevel = options.loglevel.upper()
    if options.logconfigfile:
        logging.config.fileConfig(options.logconfigfile)
    elif logLevel in [ "INFO", "DEBUG" ]:
        level = eval("logging." + logLevel)
        logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")

    if options.interface == "console":
        return scriptengine.ScriptEngine()

    exec "from " + options.interface + "toolkit import ScriptEngine"
    logEnabled = logLevel != "OFF" and not options.supported and not options.supported_html
    mapFiles = []
    if options.mapfiles:
        mapFiles = options.mapfiles.split(",")
    return ScriptEngine(uiMapFiles=mapFiles, universalLogging=logEnabled, binDir=os.path.join(install_root, "bin"))
    
def set_up_environment(options):
    if options.record:
        os.environ["USECASE_RECORD_SCRIPT"] = options.record
    elif options.supported or options.supported_html: # don't set up replay when just printing supported info
        os.environ["USECASE_RECORD_SCRIPT"] = ""
    if options.replay:
        os.environ["USECASE_REPLAY_SCRIPT"] = options.replay
    elif options.supported or options.supported_html: # don't set up replay when just printing supported info
        os.environ["USECASE_REPLAY_SCRIPT"] = ""
    if options.delay:
        os.environ["USECASE_REPLAY_DELAY"] = options.delay


def check_python_version():
    major, minor = sys.version_info[:2]
    reqMajor, reqMinor = (2, 5)
    if (major, minor) < (reqMajor, reqMinor):
        strVersion = str(major) + "." + str(minor)
        reqVersion = str(reqMajor) + "." + str(reqMinor)
        raise definitions.UseCaseScriptError, "StoryText " + definitions.__version__ + " requires at least Python " + \
            reqVersion + ": found version " + strVersion + "."

def main(install_root):
    parser = create_option_parser()
    options, args = parser.parse_args()
    set_up_environment(options)    
    try:
        check_python_version()
        import storytext
        storytext.scriptEngine = create_script_engine(options, install_root)
        if not storytext.scriptEngine.run(options, args):
            parser.print_help()
    except definitions.UseCaseScriptError, e:
        sys.stderr.write(str(e) + "\n")

