#!/usr/bin/env python

if __name__ == "__main__":
    import sys
    if "bole" in sys.argv[1]:
        sys.stderr.write("Not converted " + sys.argv[1])
    else:
        sys.stdout.write("Converted " + sys.argv[1])
