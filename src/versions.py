#!/usr/bin/python2.7

import os
import sys

from jira import JIRA

def get_credentials():
    user = os.environ["JIRA_USER"]
    password = os.environ["JIRA_PASSWORD"]

    if user is None or password is None:
        sys.stderr.write("Set JIRA_USER and JIRA_PASSWORD environment variables to authenticate.")
        sys.exit(1)

    return (user, password)

# By default, the client will connect to a JIRA instance started from the Atlassian Plugin SDK.
# See
# https://developer.atlassian.com/display/DOCS/Installing+the+Atlassian+Plugin+SDK
# for details.

options = {
    'server': 'https://issues.apache.org/jira',
    'basic_auth': get_credentials()
}

jira = JIRA(options)    # a username/password tuple

# Get the mutable application properties for this server (requires
# jira-system-administrators permission)
props = jira.application_properties()

# Find all issues reported by the admin
projects = jira.projects()
for p in projects:
    print p

sys.exit(0)
issues = jira.search_issues('assignee=admin')

# Find the top three projects containing issues reported by admin
from collections import Counter
top_three = Counter(
    [issue.fields.project.key for issue in issues]).most_common(3)
