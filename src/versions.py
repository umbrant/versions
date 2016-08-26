#!/usr/bin/env python

import os
import sys

from jira import JIRA

def get_credentials():
    user = os.environ.get("JIRA_USER", None)
    password = os.environ.get("JIRA_PASSWORD", None)

    if user is None or password is None:
        sys.stderr.write("Set JIRA_USER and JIRA_PASSWORD environment variables to authenticate.")
        sys.exit(1)

    return (user, password)

options = {
    'server': 'https://issues.apache.org/jira',
}
basic_auth = get_credentials()

jira = JIRA(options, basic_auth=basic_auth)    # a username/password tuple

# Find all issues reported by the admin
issues = []
max_results = 500
#query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion not in ("3.0.0-alpha1", "3.0.0-alpha2") and fixVersion in ("2.8.0", "2.9.0", "2.6.4", "2.7.2")"""
query = "issue = HADOOP-13409"
while True:
    print "Fetching batch of issues %d to %d" % (len(issues), len(issues)+max_results)
    batch = jira.search_issues(query, maxResults=max_results)
    issues += batch
    if len(batch) == 0 or len(issues) >= batch.total:
        break

projects = {}

for issue in issues:
    print "Updating", issue.key

    project_key = issue.fields.project.key
    if project_key not in projects:
        projects[project_key] = jira.project(project_key)
    project = projects[project_key]

    fix_versions = []
    for v in issue.fields.fixVersions:
        fix_versions.append({"name": v.name})
    print "Current fix versions:", fix_versions
    fix_versions.append({"name": "3.0.0-alpha1"})
    print "New fix versions:", fix_versions
    issue.update(fields={'fixVersions': fix_versions})

