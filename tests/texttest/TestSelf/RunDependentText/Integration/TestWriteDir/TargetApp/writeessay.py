#!/usr/bin/env python
import os

print "\nSometimes we remove line number 2...\n"

print "Sometimes we remove today's date, 2003-12-01T23:24\n"

print "We need to be able to match on trailing spaces "
print " and also on leading spaces\n"

print "Or even several lines at once, like in this table:"
print "   Here     are     some     columns"
print "   That    have    spacing   between"
print "Repeating     3     3     3     3\n"

print "Sometimes between markers, starting section"
print "Rant"
print "Rave Horribly"
print "Gibber Horribly"
print "End Section Here\n"

print "This should always go: \"" + os.getcwd() + "\""
