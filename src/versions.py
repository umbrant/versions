#!/usr/bin/env python

import os
import sys
import argparse
import logging

from jira import JIRA

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_credentials():
    user = os.environ.get("JIRA_USER", None)
    password = os.environ.get("JIRA_PASSWORD", None)

    if user is None or password is None:
        logger.error("Set JIRA_USER and JIRA_PASSWORD environment variables to authenticate.")
        sys.exit(1)

    return (user, password)

def main() :

    parser = argparse.ArgumentParser(description="Do bulk fix version updates on JIRA.")
    parser.add_argument("-f", "--force",
                        action="store_true",
                        help="If not specified, will not do any actual updates to JIRA.")
    args = parser.parse_args()

    if not args.force:
        logger.info("=================================")
        logger.info("Dry-run, will not commit changes.")
        logger.info("=================================")

    options = {
        'server': 'https://issues.apache.org/jira',
    }
    basic_auth = get_credentials()

    jira = JIRA(options, basic_auth=basic_auth)    # a username/password tuple

    # Find all issues reported by the admin
    issues = []
    max_results = 100
    # JIRAs fixed after 2.7.0 that do not have the 3.0.0-alpha1 fixVersion
    query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion not in ("3.0.0-alpha1") and fixVersion in ("2.8.0", "2.9.0", "2.6.1", "2.6.2", "2.6.3", "2.6.4", "2.7.1", "2.7.2", "2.7.3")"""
    # Test JIRA
    #query = "issue = HADOOP-13409"
    while True:
        logger.info("Fetching batch of issues %d to %d", len(issues), len(issues)+max_results-1)
        batch = jira.search_issues(query, maxResults=max_results)
        issues += batch
        if len(batch) == 0 or len(issues) >= batch.total:
            break

    projects = {}

    for issue in issues:
        logger.info("Found issue %s", issue.key)

        project_key = issue.fields.project.key
        if project_key not in projects:
            projects[project_key] = jira.project(project_key)
        project = projects[project_key]

        fix_versions = []
        for v in issue.fields.fixVersions:
            fix_versions.append({"name": v.name})
        logger.info("Cur fix versions: %s", [f["name"] for f in fix_versions])

        # Add the 3.0.0-alpha1 fixVersion
        fix_versions.append({"name": "3.0.0-alpha1"})
        # Remove any 3.0.0-alpha2 fixVersions, since we're rebranching
        fix_versions = [f for f in fix_versions if f["name"] != "3.0.0-alpha2"]

        logger.info("New fix versions: %s", [f["name"] for f in fix_versions])
        if args.force:
            logger.info("Updating %s", issue.key)
            issue.update(fields={'fixVersions': fix_versions})

if __name__ == "__main__":
    main()
