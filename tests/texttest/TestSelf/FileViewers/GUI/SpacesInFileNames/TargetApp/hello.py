#!/usr/bin/env python

print "Hello world!"

fileWithSpacesInName = open('another file.hello', 'w')
fileWithSpacesInName.write('I can write to annoying files too ...\n')
fileWithSpacesInName.close()
