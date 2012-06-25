#!/usr/bin/env python

# Interface to trac version >= 0.11. Not tested on earlier versions.

import urllib2

def findBugInfo(bugId, location, *args):
    if location and location[-1] != '/':
        location += '/'
    tracRequest = "%sticket/%s?format=tab" % (location, bugId)
    try:
        reply = urllib2.urlopen(tracRequest).readlines()
    except Exception, e:
        message = "Failed to open URL '" + tracRequest + "': " + str(e) + \
                  ".\n\nPlease make sure that bug " + bugId + " exists\n" + \
                  "and that the configuration entry 'bug_system_location' " + \
                  "points to the correct trac instance.\nThe current value is '" + location + "'."
        return "NONEXISTENT", message, False
    keys = reply[0].split('\t')
    values = ("".join(reply[1:])).split('\t')
    if len(keys) == 1 or len(keys) > len(values):
        message = "Could not parse reply from trac, maybe incompatible interface."
        return "BAD SCRIPT", message, False
    info = {'status': '', 'description': '', 'reporter': '', 'resolution': '', 'component': '', 'summary': '',
            'priority': '', 'version': '', 'milestone': '', 'owner': '', 'type': ''}
    for k, v in zip(keys, values):
        info[k.strip()] = v.strip()
    bugText = "******************************************************\n" + \
           "Ticket #%s (%s %s: %s)\n" % (bugId, info['status'], info['type'], info['resolution']) + \
           "%s\n%sticket/%s\n" % (info['summary'], location, bugId) + \
           "Reported By: %s Owned by: %s\n" % (info['reporter'], info['owner']) + \
           "Priority: %s Milestone: %s\n" % (info['priority'], info['milestone']) + \
           "Component: %s Version: %s\n" % (info['component'], info['version']) + \
           "Description:\n" + info['description'] + "\n" + \
           "******************************************************"
    return info['status'], bugText, info['status'] == "closed"

if __name__ == "__main__": # pragma: no cover - test code
    import sys
    for item in findBugInfo(sys.argv[1], sys.argv[2]):
        print item
