#!/usr/bin/env python

import argparse
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

        options = {
            'server': 'https://issues.apache.org/jira',
        }

        basic_auth = None
        if args.force:
            basic_auth = get_credentials()

        jira = JIRA(options, basic_auth=basic_auth)    # a username/password tuple

        # Find all issues reported by the admin
        issues = []
        max_results = 100
        # JIRAs fixed after 2.7.0 that do not have the 3.0.0-alpha1 fixVersion
        query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion not in ("3.0.0-alpha1") and fixVersion in ("2.8.0", "2.9.0", "2.6.1", "2.6.2", "2.6.3", "2.6.4", "2.7.1", "2.7.2", "2.7.3") and resolution=Fixed"""
        # Test JIRA
        #query = "issue = HADOOP-13409"
        #query = "issue in (HADOOP-12787, HADOOP-12345, HADOOP-13438, YARN-1279, YARN-1234)"
        while True:
            logger.info("Fetching batch of issues %d to %d", len(issues), len(issues)+max_results-1)
            batch = jira.search_issues(query, startAt=len(issues), maxResults=max_results)
            issues += batch
            if len(batch) == 0 or len(issues) >= batch.total:
                break

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
        parser.add_argument("--fixup-commits",
                            type=file,
                            help="File containing manual mappings of commits to certain JIRAs. This is used to correct typos in git log.")
        parser.add_argument("--whitelist-jiras",
                            type=file,
                            help="File containing JIRAs to whitelist.")

    def run(self, args):
        # Parse fixup information
        fixups = {}
        if args.fixup_commits:
            for k,v in json.load(args.fixup_commits).iteritems():
                fixups[k] = v
        repo = Repo(args.source_dir)
        commits_by_id = {}
        unknown_commits = []
        pattern = re.compile("(HADOOP|HDFS|MAPREDUCE|YARN)-[0-9]+")
        # Index the commits by JIRA #, including fixup information
        for commit in repo.iter_commits(args.start_ref + "..." + args.end_ref):
            # Fixup information overrides commit message
            jira_id = fixups.get(commit.hexsha)
            if not jira_id:
                match = pattern.match(commit.message)
                if not match:
                    unknown_commits.append(commit)
                    continue
                jira_id = match.group(0)
            commits_by_id.get(jira_id, []).append(commit)

        print "Number knowns:", len(commits_by_id)
        print "Number unknowns:", len(unknown_commits)
        for commit in unknown_commits:
            print commit.hexsha, commit.message.encode("utf-8").split("\n")[0]

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
