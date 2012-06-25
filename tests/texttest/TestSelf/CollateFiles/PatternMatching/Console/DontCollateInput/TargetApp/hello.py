#!/usr/bin/env python

print 'Hello'
editFile = open("input_dir/editfile", "a")
editFile.write("Line\n")
writeFile = open("input_dir/writefile", "w")
writeFile.write("Line\n")
