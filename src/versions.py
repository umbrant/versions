#!/usr/bin/env python

import argparse
import json
import logging
import os
import re
import sys

from git import Repo
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


def get_jira(auth=False):
    options = {
        'server': 'https://issues.apache.org/jira',
    }

    basic_auth = None
    if auth:
        basic_auth = get_credentials()

    jira = JIRA(options, basic_auth=basic_auth)
    return jira


def jira_query(jira, query):
    issues = []
    max_results = 100
    while True:
        logger.info("Fetching batch of issues %d to %d", len(issues), len(issues)+max_results-1)
        batch = jira.search_issues(query, startAt=len(issues), maxResults=max_results)
        issues += batch
        if len(batch) == 0 or len(issues) >= batch.total:
            break

    return issues


class UpdateRunner:

    NAME = "update"

    def __init__(self):
        pass

    @classmethod
    def add_parser(cls, subparsers):
        parser = subparsers.add_parser(cls.NAME)
        parser.add_argument("-f", "--force",
                            action="store_true",
                            help="If not specified, will not do any actual parsers to JIRA.")
        parser.add_argument("-o", "--output",
                            help="Log changes to an external file.")
        parser.add_argument("-e", "--excludes",
                            help="Exclude file containing one JIRA # (e.g. YARN-4321) per line. " +
                            "Excluded JIRAs will not be parserd.")

    def run(self, args):
        outfile = None
        if args.output is not None:
            logger.info("Logging changes to output file %s", args.output)
            outfile = open(args.output, "w")

        excludes = []
        if args.excludes is not None:
            with open(args.excludes, "r") as e:
                excludes = [x[:-1] for x in e.readlines()]
            logger.info("Will exclude %d JIRAs: %s", len(excludes), ", ".join(excludes))

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

        jira = get_jira(auth=True)

        # JIRAs fixed after 2.7.0 that do not have the 3.0.0-alpha1 fixVersion
        query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion not in ("3.0.0-alpha1") and fixVersion in ("2.8.0", "2.9.0", "2.6.1", "2.6.2", "2.6.3", "2.6.4", "2.7.1", "2.7.2", "2.7.3") and resolution=Fixed"""
        # Test JIRA
        #query = "issue = HADOOP-13409"
        #query = "issue in (HADOOP-12787, HADOOP-12345, HADOOP-13438, YARN-1279, YARN-1234)"
        issues = jira_query(jira, query)

        projects = {}

        for issue in issues:
            if issue.key in excludes:
                logger.debug("%s is excluded, skipping", issue.key)
                continue

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


class ValidateRunner:

    NAME = "validate"

    def __init__(self):
        pass

    @classmethod
    def add_parser(cls, subparsers):
        parser = subparsers.add_parser(cls.NAME)
        parser.add_argument("--source-dir",
                            default=os.getcwd(),
                            help="Location of source directory. Defaults to the current working directory.")
        parser.add_argument("--start-ref",
                            required=True,
                            help="Starting git ref.")
        parser.add_argument("--end-ref",
                            default="HEAD",
                            help="Ending git ref. Defaults to HEAD.")
        parser.add_argument("--fix-version",
                            required=True,
                            help="Corresponding fix version on JIRA.")
        parser.add_argument("--fixups",
                            type=file,
                            help="File containing manual mappings of" \
                            + " commits to certain JIRAs. This is used to correct typos in git log.")
        parser.add_argument("--whitelist-jiras",
                            type=file,
                            help="File containing JIRAs to whitelist.")

    def run(self, args):
        # Parse fixup information
        fixups = {}
        ignore = []
        if args.fixups:
            d = json.load(args.fixups)
            if "fixups" in d:
                for k,v in d["fixups"].iteritems():
                    fixups[k] = v
            if "ignore" in d:
                for k in d["ignore"]:
                    ignore.append(k)
        repo = Repo(args.source_dir)

        # Get the commits
        commits = []
        commits.extend(repo.iter_commits(args.start_ref + "..." + args.end_ref))

        to_skip = set(ignore)

        # Filter out reverted commits
        revert_pattern = re.compile("This reverts commit ([0-9a-f]+)")
        for commit in commits:
            match = revert_pattern.search(commit.message)
            if match:
                # Remove both the revert and the reverted commit
                to_skip.add(commit.hexsha)
                to_skip.add(match.group(1))

        # Filter out merge commits
        merge_pattern = re.compile("Merge branch '[a-zA-Z0-9-]+' into [a-zA-Z0-9-]+")
        for commit in commits:
            match = merge_pattern.search(commit.message)
            if match:
                to_skip.add(commit.hexsha)

        # Index the commits by JIRA #, including fixup information
        commits_by_id = {}
        pattern = re.compile("(HADOOP|HDFS|MAPREDUCE|YARN)-[0-9]+")
        unidentified_commits = []
        for commit in commits:
            # Skip reverted commits
            if commit.hexsha in to_skip:
                continue
            # Fixup information overrides commit message
            jira_id = fixups.get(commit.hexsha)
            if not jira_id:
                match = pattern.match(commit.message)
                if not match:
                    # Try to detect a revert
                    match = revert_pattern.match(commit.message)
                    if not match:
                        unidentified_commits.append(commit)
                        continue
                    # Handle the revert
                jira_id = match.group(0)
            commits = commits_by_id.get(jira_id, [])
            commits.append(commit)
            commits_by_id[jira_id] = commits

        for commit in unidentified_commits:
            print commit.hexsha, commit.message.encode("utf-8")

        print "Number commits in skip list:", len(to_skip)
        print "Number identified commits:", len(commits_by_id)
        print "Number unidentified commits:", len(unidentified_commits)

        return

        # Get JIRA issues for the fix version
        jira = get_jira()
        query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion in ("%s") and resolution=Fixed""" % (args.fix_version,)
        issues = jira_query(jira, query)
        issues_by_id = {}
        for issue in issues:
            issues_by_id[issue.key] = issue

        issues_missing_commits = []
        for issue in issues:
            if issue.key not in commits_by_id:
                issues_missing_commits.append(issue)
        commits_missing_issues = []
        for commit in commits_by_id:
            if commit not in issues_by_id:
                commits_missing_issues.append(commit)

        print "Number identified commits:", len(commits_by_id)
        print "Number unidentified commits:", len(unidentified_commits)
        print "Number issues with matching commit(s):", len(issues_by_id)
        print "Number issues with missing commits:", len(issues_missing_commits)
        print "Number commits with missing issues:", len(commits_missing_issues)


def parse_args(runners):
    parser = argparse.ArgumentParser(description="Perform version-related operations on JIRAs.")
    subparsers = parser.add_subparsers(dest="subparser_name",
                                       help="subparser help")

    UpdateRunner.add_parser(subparsers)
    ValidateRunner.add_parser(subparsers)

    # Parse and return args
    args = parser.parse_args()
    return args

def main():

    runners = [UpdateRunner, ValidateRunner]
    args = parse_args(runners)
    for runner in runners:
        if runner.NAME == args.subparser_name:
            sys.exit(runner().run(args))


if __name__ == "__main__":
    main()
