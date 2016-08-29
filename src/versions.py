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

def main():

    parser = argparse.ArgumentParser(description="Do bulk fix version updates on JIRA.")
    parser.add_argument("-f", "--force",
                        action="store_true",
                        help="If not specified, will not do any actual updates to JIRA.")
    parser.add_argument("-o", "--output",
                        help="Log changes to an external file.")
    args = parser.parse_args()

    outfile = None
    if args.output is not None:
        logger.info("Logging changes to output file %s", args.output)
        outfile = open(args.output, "w")

    if args.force:
        logger.info("=================================================")
        logger.info("--force specified, will commit changes!")
        if outfile is None:
            logger.info("Recommend also specifying --output for safety.")
        logger.info("Press enter to confirm, or Ctrl-C to cancel.")
        logger.info("================================================")
        raw_input()
    else:
        logger.info("Dry-run, will not commit changes.")

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
        batch = jira.search_issues(query, startAt=len(issues), maxResults=max_results)
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

        # Print old fix versions
        logger.info("Old fix versions: %s", [f["name"] for f in fix_versions])
        if outfile is not None:
            outfile.write(issue.key + " old fix versions: ")
            outfile.write(",".join([f["name"] for f in fix_versions]))
            outfile.write("\n")

        # Add the 3.0.0-alpha1 fixVersion if not present
        if "3.0.0-alpha1" not in [f["name"] for f in fix_versions]:
            fix_versions.append({"name": "3.0.0-alpha1"})
        # Remove any 3.0.0-alpha2 fixVersions, since we're rebranching
        fix_versions = [f for f in fix_versions if f["name"] != "3.0.0-alpha2"]

        logger.info("New fix versions: %s", [f["name"] for f in fix_versions])
        if outfile is not None:
            outfile.write(issue.key + " new fix versions: ")
            outfile.write(",".join([f["name"] for f in fix_versions]))
            outfile.write("\n")

        if args.force:
            logger.info("Updating %s", issue.key)
            issue.update(fields={'fixVersions': fix_versions})

    if outfile is not None:
        outfile.close()

if __name__ == "__main__":
    main()
