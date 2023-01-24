from optparse import OptionParser
from common import shared
import urllib3
import re
import json
import sys
import os
import time
import datetime

def getval(object):
    return object

def saveFilters(name, filters):
    with open(name,'w') as outfile:
        json.dump(filters, outfile,indent=4, sort_keys=True)

def loadConstants():
    constants = {}
    if os.path.isfile("constants.json"):
        print("Loading constants from constants.json")
        constantdef = json.load(open("constants.json", 'r'))
        for name, fields in constantdef.items():
            method = getattr(sys.modules[__name__], fields['function'])
            del fields['function']
            constants[name] = method(**fields)
            print("  " + name + " -> " + str(constants[name]))
    
    return constants


def isCodefrozenToday(v, flag=True):
    """Sees if v is codefrozen and return value of flag (default true). If codefrozen cannot be detected it will return opposite of the flag."""
    if 'description' in v:
        result = re.search(".*codefreeze:.*([0-9]{4}.[0-9]{2}.[0-9]{2}).*", v['description'])
        if result:
            try:
                ts = time.mktime(datetime.datetime.strptime(result.group(1), "%Y/%m/%d").timetuple())
            except ValueError:
                ts = time.mktime(datetime.datetime.strptime(result.group(1), "%Y-%m-%d").timetuple())
            if ts <= time.time():
                return flag

    return not flag

def hasFieldOrNot(field, flag,v):
    #print "Checking if " + field + " = " + str(flag) + " when it is " + v.get(field)
    if flag:
        r = field in v
    else:
        r = field not in v
    #print "result : " + str(r)
    return r

def dumpVersions(foundversions):
    if foundversions:
        return str(len(foundversions))  + " @ " + ", ".join(map(lambda v: v['name'], foundversions))
    else:
        # print("foundversions is null")
        return ""


def listVersions(project, pattern=".*", released=None, hasReleaseDate=None, archived=None, hasStartDate=None, codefrozen=None, lowerLimit=None, upperLimit=None, index=None):
    """Return list of versions for a specific project matching a pattern and a list of optional filters.

           arguments:
            project -- the jira project key (i.e. 'CRW') (required)
            pattern -- regular expression that the version name should match (i.e. '3.5.*') (default=.*)
            released -- boolean to state if the version should be released or not. (default=None)
            archived -- boolean to state if the version should be archived or not. (default=None)
            hasStartDate -- boolean to state if the version should have a start date. (default=None)
            hasReleaseDate -- boolean to state if the version should have a released date. (default=None)
            codefrozen -- boolean if description of version contains (codefreeze: <date>) and date has occurred true will include it otherwise exclude it. 
            upperLimit -- upper limit (default=None)
            lowerLimit -- lower limit (default=None)
            index -- integer to state which index to get (supports negative indexing too, -1=last element), if index out of range nothing is returned. (default=None)

            examples:
            listVersions("CRW", "3.5.*") -- versions in CRW starting with "3.5."
            listVersions("CRW", "3.5.*", upperLimit=2) -- first two version of 3.5.*
            listVersions("CRW", "3.5.*", released=False, upperLimit=2) -- first two version that are released in 3.5.*
            listVersions("CRW", "3.5.*", released=False) -- non-released 3.5.* versions
            listVersions("CRW", "3.5.*|3.6.*", released=False, hasReleaseDate=True) -- non-released that has release date in either 3.5 or 3.6 streams
            listVersions("CRW", "3.5.*|3.6.*", released=False, hasStartDate=True) -- non-released that has start date in either 3.5 or 3.6 streams
            listVersions("CRW", ".*", archived=True, hasReleaseDate=True, lowerLimit=2, lowerLimit=4)
    """

    versions = shared.jiraquery(options,"/rest/api/latest/project/" + project + "/versions")
    if options.verbose:
        print("pattern: " + pattern)
        #print codefrozen
        
    versionmatch = re.compile(pattern)
    foundversions = []
    for version in versions:
        if versionmatch.match(version['name']):
            foundversions.append(version)

    if options.verbose:
        print("  after versionmatch: " + str(dumpVersions(foundversions)))
    
    if released is not None:
        foundversions = list(filter(lambda v: released == v['released'], foundversions))
        if options.verbose:
            print("  after released ("+str(released)+"):")
            print(dumpVersions(foundversions))
    
    if hasReleaseDate is not None:
        foundversions = list(filter(lambda v: hasFieldOrNot('releaseDate', hasReleaseDate, v), foundversions))
        if options.verbose:
            print("  after hasReleaseDate: " + str(dumpVersions(foundversions)))
    
    if hasStartDate is not None:
        foundversions = list(filter(lambda v: hasFieldOrNot('startDate', hasStartDate, v), foundversions))
        if options.verbose:
            print("  after hasStartDate: " + str(dumpVersions(foundversions)))
    
    if archived is not None:
        foundversions = list(filter(lambda v: archived == v['archived'], foundversions))
        if options.verbose:
            print("  after archived: " + str(dumpVersions(foundversions)))

    if codefrozen is not None:
        foundversions = list(filter(lambda v: isCodefrozenToday(v, codefrozen), foundversions))
        if options.verbose:
            print("after codefrozen: " + str(dumpVersions(foundversions)))
    
    if upperLimit or lowerLimit:
        foundversions = foundversions[lowerLimit:upperLimit]
        if options.verbose:
            print("after limits: " + str(dumpVersions(foundversions)))
    
    if index is not None:
        try:
            foundversions = [foundversions[index]]
        except IndexError:
            foundversions = []
        if options.verbose:
            print("after index: " + str(dumpVersions(foundversions)))
    
    foundversions = map(lambda v: v['name'], foundversions)
    
    return ", ".join(f"'{w}'" for w in foundversions)

    

usage = "usage: %prog -u <jirauser> -k <jiratoken> -f <filters.json>\nCreate/maintain set of filters defined in filters.json."

parser = OptionParser(usage)

#todo: move the shared options to common ?
parser.add_option("-u", "--user", dest="jirauser", help="jirauser")
parser.add_option("-p", "--pwd", dest="jirapwd", help="jirapwd")
parser.add_option("-k", "--token", dest="jiratoken", help="jiratoken")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.redhat.com", help="Jira instance")
parser.add_option("-f", "--filters", dest="filterfiles", default="filters.json", help="comma separated list of filters to setup")
parser.add_option("-v", "--debug", dest="verbose", action="store_true", help="more verbose logging")
(options, args) = parser.parse_args()
    
if (not options.jirauser or (not options.jirapwd and not options.jiratoken)):
    parser.error("Must set -u jirauser and either -p jirapwd or -k jiratoken")

if options.filterfiles:
    #print "Force enabling global shared filters. Will not have any effect if user is not allowed to globally share objects in jira."
    #shared.jiraupdate(options, "/rest/api/latest/filter/defaultShareScope", { 'scope': 'GLOBAL' })

    constants = loadConstants()

    allfilters = {}
    filterfiles = options.filterfiles.split(',')
    print("")
    for filterfile in filterfiles:
        print("Processing filters found in " + filterfile)
        filters = json.load(open(filterfile, 'r'))

        newfilters = filters.copy()
        for name, fields in filters.items():
            try:
                print("")
                print("filter " + name)
                data = {
                    'name': name,
                    'description': fields['description'],
                    'jql': fields['jql'] % constants,
                    'favourite' : 'true'
                }
                
                if 'id' in fields:
                    print('  updating filter ' + name + " -> " + data['jql'])
                    fields['id'] = shared.jiraupdate(options, "/rest/api/latest/filter/" + fields['id'], data)['id']
                else:
                    print('creating filter ' + name + " -> " + data['jql'])
                    fields['id'] = shared.jirapost(options, "/rest/api/latest/filter", data)['id']
                allfilters[name] = fields
                newfilters[name] = fields
                saveFilters(filterfile, newfilters) # saving every succesful iteration to not loose a filter id 
            except urllib3.exceptions.HTTPError as e:
                print("Problem with setting up filter %s with JQL = %s" % (data['name'], data['jql']))

    print("\nJira filters in asciidoc:\n")
    print("[options=\"header\"]")
    print(".Jira Filters")
    print("|===")
    print("|Name|  Description| Query") 
    for name, fields in allfilters.items():
        print("| https://issues.redhat.com/issues/?filter="+ fields['id'] + "[" + name + "] | " + fields['description'] + "| " + fields['jql'])
