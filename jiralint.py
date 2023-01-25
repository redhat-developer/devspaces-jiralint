import urllib, sys, os
##import yaml  not on rhel4
import json
import smtplib
import datetime
from datetime import timedelta
## from dateutil.parser import parse not on rhel6
import pprint
from xml.dom.minidom import Document
from optparse import OptionParser
from common import shared

pp = pprint.PrettyPrinter(indent=4)

def fetch_email(username, fallback, email_addresses):
    if username in email_addresses:
        return email_addresses[username]
    else:
        found = None
        payload = {'username': username}
        user_data = shared.jiraquery(options, "/rest/api/latest/user?" + urllib.parse.urlencode(payload))
        if 'emailAddress' in user_data:
            found = str(user_data['emailAddress'])
            email_addresses[username]=found
        else:
            print('No email found for ' + username + ' using ' + str(fallback))
            found = fallback
            # don't cache if not found
        return found
                                        
def xstr(s):
    if s is None:
        return 'None'
    else:
        return str(s)

def email_array_to_string(email_array):
    email_string = ""
    for name in email_array:
        email_string = email_string + (", " if email_string else "") + name + " <" + email_array[name] + ">"
    return email_string

# thanks to http://guidetoprogramming.com/joomla153/python-scripts/22-send-email-from-python
def mailsend (smtphost, from_email, to_email, subject, message, recipients_list, options):
    

    header = 'To: ' + recipients_list + '\n' + \
        'From: ' + from_email + '\n' + \
        'Subject: ACTION REQUIRED: ' + subject + '\n\n'

    message = message.decode('utf8', 'replace')
    msg = header + '\n' + message
    msg = msg.encode('utf8', 'replace')
    if options.verbose:
        print(msg.decode('utf8'))
    if not options.dryrun:
        server = smtplib.SMTP(smtphost, 25)
        server.sendmail(from_email, recipients_list, msg)
        server.close()

def render(issue_type, issue_description, jira_env, issues, jql, options, email_addresses, components):
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    emails_to_send = {}

    if len(issues) > 0:
        for i, v in enumerate(issues):
            
            fields = v['fields']
            jira_key = v['key']

            # For available field names, see the variables in
            # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
            #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
            # print fields['components']

            component_details = []
            component_lead_name = ""
            component_lead_email = ""
            component_lead_names = ""
            for component in fields['components']:
                # print component['id']
                # https://issues.redhat.com/rest/api/latest/component/12311294
                if component['id'] in components:
                    component_data = components[component['id']]
                else:
                    # print 'Query ' + component['name'] + ' component lead'
                    component_data = shared.jiraquery(options, "/rest/api/latest/component/" + component['id'])
                    components[component['id']] = component_data
                    
                component_name = str(component_data['name'])
                if not 'lead' in component_data.keys():
                    raise Exception('[ERROR] No component lead set for component = ' + component_name + ' on issue ' + jira_key + 
                        '.\n\n[ERROR] Contact an administrator to update https://issues.redhat.com/plugins/servlet/project-config/CRW/components')
                component_lead_name = str(component_data['lead']['name'])
                component_lead_names += "-" + xstr(component_lead_name)
                component_lead_email = fetch_email(component_lead_name, options.unassignedjiraemail, email_addresses)
                component_details.append({'name': component_name, 'lead': component_lead_name, 'email': component_lead_email})
            fix_version = ""
            for version in fields['fixVersions']:
                fix_version += '_' + version['name']
            fix_version = fix_version[1:]
            if fix_version == "":
                if issue_type == "No fix version":
                    fix_version = ""
                else:
                    fix_version=".nofixversion"
            else:
                fix_version = "." + xstr(fix_version)

            recipients = {}
            assignees = {}
            assignee_name = "Nobody"
            assignee_email = str(options.unassignedjiraemail)
            if fields['assignee']:
                assignee_name = str(fields['assignee']['name'])
                if 'emailAddress' in fields['assignee']:
                    assignee_email = str(fields['assignee']['emailAddress'])
                else:
                    assignee_email = fetch_email(assignee_name, None, email_addresses)
                    if not assignee_email:
                        print('No email found for assignee: ' + assignee_name)
                assignees[assignee_name] = assignee_email
                recipients[assignee_name] = assignee_email
                if not assignee_name in email_addresses:
                    email_addresses[assignee_name] = assignee_email

            # TODO handle array of components
            elif component_details:
                for component_detail in component_details:
                    # print component_detail
                    recipients[component_detail['lead']] = component_detail['email']
            else:
                # default assignee - send to mailing list if no component set
                recipients["Nobody"] = str(options.unassignedjiraemail)

            # print recipients

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", jira_key)
            testcase.setAttribute("name", issue_type.lower().replace(" ","") + xstr(fix_version) + "." + assignee_name + xstr(component_lead_names))

            o = urllib.parse.urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + jira_key

            error = doc.createElement("error")

            lastupdate = datetime.datetime.now() - datetime.datetime.strptime(fields['updated'][:-5], "%Y-%m-%dT%H:%M:%S.%f" ).replace(tzinfo=None)

            error.setAttribute("message", "\n* [" + assignee_email + "] " + issue_type + " for " + jira_key)

            component_name = ""
            lead_info = ""
            assignee_info = ""
            if component_details:
                for component_detail in component_details:
                    component_name = component_name + (", " if component_name else "") + component_detail['name']
                    lead_info = lead_info + (", " if lead_info else "") + component_detail['lead'] + " <" + component_detail['email'] + ">"

            assignee_info = email_array_to_string(assignees)
            # print assignee_info

            error_text = "\n" + str(url) + "\n" + \
                "Summary: " + str(fields['summary']) + "\n\n" + \
                ("Assignee(s): " + str(assignee_info) if assignee_info else "Assignee: None set.") + "\n" + \
                ("Lead(s): " + str(lead_info) + "\n" if lead_info else "") + \
                ("Component(s): " + str(component_name) if component_name else "Component: None set - please fix.") + "\n" + \
                "Problem: " + str(issue_type) + " - " + str(issue_description) + "\n" + \
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n"

            error_text_node = doc.createTextNode(error_text)
            error.appendChild(error_text_node)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)

            subject = "\n* " + issue_type + " for " + jira_key
  
            # load email content into a dict(), indexed by email recipient & JIRA; for issues w/ more than one component, each component lead will get an email
            for name in recipients:
                if not recipients[name] in emails_to_send:
                    emails_to_send[recipients[name]] = {}
                emails_to_send[recipients[name]][jira_key] = {'issue_summary': str(fields['summary']), 'message': subject + '\n' + error_text, 'recipients': name + " <" + recipients[name] + ">"}
                #print emails_to_send[recipients[name]][jira_key]

    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", issue_type)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
 
    print('  Write to ' + issue_type.lower().replace(" ","") + "-test.xml")
    output = open(issue_type.lower().replace(" ","") + "-test.xml", 'w')
    output.write(doc.toprettyxml(indent="  ").encode('utf8', 'replace').decode('utf8'))

    # send emails & log to file
    log = ''
    if options.fromemail:
        if len(emails_to_send) > 0:
            for i, assignee_email in enumerate(emails_to_send):
                problem_count = str(len(emails_to_send[assignee_email]))
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                entry = ("Prepare (but do not send)" if options.dryrun else "Send") + " email with " + problem_count + \
                    " issue(s) to: " + (options.toemail + " (not " + assignee_email + ")" if options.toemail else assignee_email)
                print(entry)
                log = log + entry + "\n\n" + options.jiraserver + "/issues/?jql=" + urllib.parse.quote_plus(jql) + "\n\n"
                message = ''
                o = urllib.parse.urlparse(v['self'])
                url = o.scheme + "://" + o.netloc + "/browse/"
                for j, jira_key in enumerate(emails_to_send[assignee_email]):
                    print(" * " + url + jira_key + " - " + emails_to_send[assignee_email][jira_key]['issue_summary'])
                    message = message + emails_to_send[assignee_email][jira_key]['message']
                    log = log + emails_to_send[assignee_email][jira_key]['message']
                    # print emails_to_send[assignee_email][jira_key]['recipients']

                # wrap generated message w/ header and footer
                message = "This email is the result of a query to locate stalled/invalid jiras. Please fix them. Thanks!" + \
                    "\n\nGlobal Query:   "  + options.jiraserver + "/issues/?jql=" + urllib.parse.quote_plus(jql) +  \
                    "\n\nPersonal Query: "  + options.jiraserver + "/issues/?jql=" + urllib.parse.quote_plus(jql + " AND assignee = currentUser()") + \
                    "\n\n----------------------------\n\n" + message
                # send to yourself w/ --toemail override, or else send to actual recipient
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                mailsend (options.smtphost, 
                    options.fromemail, 
                    (options.toemail if options.toemail else assignee_email), 
                    problem_count + ' issue' + ('s' if len(emails_to_send[assignee_email]) > 1 else '') + ' with ' + issue_type.lower(), 
                    message.encode('utf8','replace'),
                    emails_to_send[assignee_email][jira_key]['recipients'], 
                    options)
    
    if log:
        output = open(issue_type.lower().replace(" ","") + ".log", 'w')
        output.write(log.encode('utf8', 'replace').decode('utf8'))

    return email_addresses

usage = "usage: %prog -u <jirauser> -k <jiratoken> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="jirauser", help="username")
parser.add_option("-p", "--pwd", dest="jirapwd", help="password")
parser.add_option("-k", "--token", dest="jiratoken", help="token")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.redhat.com", help="Jira instance")
parser.add_option("-l", "--limit", dest="maxresults", default=200, help="maximum number of results to return from json queries (default 200)")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
parser.add_option("-f", "--fromemail", dest="fromemail", default=None, help="email address from which to send mail; if omitted, no mail will be sent")
parser.add_option("-t", "--toemail", dest="toemail", default=None, help="email address override to which to send all mail; if omitted, send to actual JIRA assignees")
parser.add_option("-n", "--unassignedjiraemail", dest="unassignedjiraemail", default=None, help="email to use for unassigned JIRAs; required if fromemail is specified")
parser.add_option("-m", "--smtphost", dest="smtphost", default=None, help="smtp host to use; required if fromemail is specified")
parser.add_option("-d", "--dryrun", dest="dryrun", action="store_true", help="do everything but actually sending mail")
parser.add_option("-v", "--debug", dest="verbose", action="store_true", help="dump email bodies to console")

(options, args) = parser.parse_args()

if (not options.jirauser or not options.jirapwd) and "userpass" in os.environ:
    # check if os.environ["userpass"] is set and use that if defined
    #sys.exit("Got os.environ[userpass] = " + os.environ["userpass"])
    userpass_bits = os.environ["userpass"].split(":")
    options.jirauser = userpass_bits[0]
    options.jirapwd = userpass_bits[1]

if (not options.jirauser or (not options.jirapwd and not options.jiratoken)):
    parser.error("Must set -u jirauser and either -p jirapwd or -k jiratoken")

if options.fromemail and (not options.unassignedjiraemail or not options.smtphost):
    parser.error("Must set both --unassignedjiraemail (-n) and --smpthost (-m) to send mail")

# store an array of username : email_address and componentid: component data we can use as a lookup table
email_addresses = {}
components = {}
    
if options.reportfile:
    print("Using reports defined in " + options.reportfile)
    reports = json.load(open(options.reportfile, 'r'))

    for report in reports:
        print("")
        for issue_type,fields in report.items():
            if options.verbose:
                print("Check for '"  + issue_type.lower() + "': https://issues.redhat.com/issues/?jql=" + urllib.parse.quote(fields['jql']))
            payload = {'jql': fields['jql'], 'maxResults' : options.maxresults}
            data = shared.jiraquery(options, "/rest/api/latest/search?" + urllib.parse.urlencode(payload))
            if 'issues' in data:
                print(str(len(data['issues'])) + " issues found with '" + issue_type.lower() + "': https://issues.redhat.com/issues/?jql=" + urllib.parse.quote(fields['jql']))
                if options.verbose:
                    print(data)
                    print(options)
                email_addresses = render(issue_type, str(fields['description']), data, data['issues'], fields['jql'], options, email_addresses, components)
            else:
                print("No issues found for '"  + issue_type.lower() + "': https://issues.redhat.com/issues/?jql=" + urllib.parse.quote(fields['jql']))
else:
    print("Generating based on .json found on standard in")
    data = json.load(sys.stdin)
    email_addresses = render('stdin', 'Query from standard in.', data, data['issues'], None, options, email_addresses, components)

