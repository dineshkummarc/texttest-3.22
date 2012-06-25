#!/usr/bin/env python
from distutils.core import setup
from distutils.command.install_scripts import install_scripts
import sys
sys.path.insert(0, "lib")
from storytext import __version__
import os

mod_files = [ "ordereddict" ]
if sys.version_info[:2] < (2, 6):
    mod_files.append("ConfigParser26")

scripts = ["bin/storytext"]
jython = os.name == "java"
if jython:
    # Revolting way to check if we're on Windows! Neither os.name nor sys.platform help when using Jython
    windows = os.pathsep == ";"
else:
    # Does not run under Jython, uses GTK
    scripts.append("bin/usecase_name_chooser")
    windows = os.name == "nt"

# Lifted from bzr setup.py, use for Jython on Windows which has no native installer
class windows_install_scripts(install_scripts):
    """ Customized install_scripts distutils action.
    Create storytext.bat for win32.
    """
    def run(self):
        install_scripts.run(self)   # standard action
        for script in scripts:
            localName = os.path.basename(script)
            try:
                bin_dir = os.path.join(sys.prefix, 'bin')
                script_path = self._quoted_path(os.path.join(bin_dir, localName))
                python_exe = self._quoted_path(sys.executable)
                args = '%*'
                batch_str = "@%s %s %s" % (python_exe, script_path, args)
                batch_path = os.path.join(bin_dir, localName + ".bat")
                f = file(batch_path, "w")
                f.write(batch_str)
                f.close()
                print "Created:", batch_path
            except Exception, e:
                print "ERROR: Unable to create %s: %s" % (batch_path, e)

    def _quoted_path(self, path):
        if ' ' in path:
            return '"' + path + '"'
        else:
            return path

def make_windows_script(src):
    outFile = open(src + ".py", "w")
    outFile.write("#!python.exe\nimport site\n\n")
    outFile.write(open(src).read())
			
command_classes = {}
if windows:
	if jython:
		command_classes = {'install_scripts': windows_install_scripts}
	else:
		newscripts = []
		for script in scripts:
			make_windows_script(script)
			newscripts.append(script + ".py")
			newscripts.append(script + ".exe")
		scripts = newscripts


setup(name='StoryText',
      version=__version__,
      author="Geoff Bache",
      author_email="geoff.bache@pobox.com",
      url="http://www.texttest.org/index.php?page=ui_testing",
      description="An unconvential GUI-testing tool for UIs written with PyGTK, Tkinter, wxPython, Swing, SWT or Eclipse RCP",
      long_description='StoryText is an unconventional GUI testing tool, with support for PyGTK, Tkinter, wxPython, Swing, SWT and Eclipse RCP. Instead of recording GUI mechanics directly, it asks the user for descriptive names and hence builds up a "domain language" along with a "UI map file" that translates it into the current GUI layout. The point is to reduce coupling, allow very expressive tests, and ensure that GUI changes mean changing the UI map file but not all the tests. Instead of an "assertion" mechanism, it auto-generates a log of the GUI appearance and changes to it. The point is then to use that as a baseline for text-based testing, using e.g. TextTest. It also includes support for instrumenting code so that "waits" can be recorded, making it far easier for a tester to record correctly synchronized tests without having to explicitly plan for this.',
      packages=["storytext", "storytext.gtktoolkit", "storytext.gtktoolkit.simulator", "storytext.gtktoolkit.describer",
                "storytext.javaswttoolkit", "storytext.javarcptoolkit", "storytext.javageftoolkit", "storytext.javaswingtoolkit" ],
      package_dir={ "" : "lib"},
      py_modules=mod_files,
      classifiers=[ "Programming Language :: Python",
                    "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
                    "Operating System :: OS Independent",
                    "Development Status :: 5 - Production/Stable",
                    "Environment :: X11 Applications :: GTK",
                    "Environment :: Win32 (MS Windows)",
                    "Environment :: Console",
                    "Intended Audience :: Developers",
                    "Intended Audience :: Information Technology",
                    "Topic :: Software Development :: Testing",
                    "Topic :: Software Development :: Libraries :: Python Modules" ],
      scripts=scripts,
      cmdclass=command_classes
      )
