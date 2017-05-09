#!/usr/bin/env python

import argparse
import logging
import os
import pickle
import re
import sys
import yaml

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


class PickleCommit:
    def __init__(self, commit):
        self.message = commit.message
        self.hexsha = commit.hexsha


class PickleIssue:
    def __init__(self, issue):
        self.key = issue.key

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
        parser.add_argument("--fix-version",
                            required=True,
                            help="Corresponding fix version on JIRA.")
        parser.add_argument("--pickle",
                            action="store_true",
                            help="Write out intermediate data. Pair it with --unpickle for debugging.")
        parser.add_argument("--unpickle",
                            action="store_true",
                            help="Read in intermediate data. Pair it with --pickle for debugging.")

    def run(self, args):
        # Parse version metadata information from external file
        fixups = {}
        ignore = []
        ignore_jiras = []
        start_ref = ""
        end_ref = ""

        metadata_path = "metadata/" + args.fix_version + ".yaml"
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as r:
                d = yaml.load(r)
                start_ref = d.get("start_ref", "")
                end_ref = d.get("end_ref", "")
                if "fixups" in d:
                    for k,v in d["fixups"].iteritems():
                        fixups[k] = v
                if "ignore" in d:
                    for k in d["ignore"]:
                        ignore.append(k)
                if "ignore_jiras" in d:
                    for k in d["ignore_jiras"]:
                        ignore_jiras.append(k)

        else:
            print "No metadata file found for fix version: ", args.fix_version
            print "You might want to create one."

        repo = Repo(args.source_dir)

        # Get the commits
        commits = []

        pickle_commits_name = "commits.pickle"
        if args.unpickle and os.path.exists(pickle_commits_name):
            print "Loading commit data from", pickle_commits_name
            with open(pickle_commits_name, "rb") as r:
                commits = pickle.load(r)
        else:
            for c in repo.iter_commits(start_ref + "..." + end_ref):
                commit = PickleCommit(c)
                commits.append(commit)

        if args.pickle:
            print "Writing commit data to", pickle_commits_name
            with open(pickle_commits_name, "wb") as w:
                pickle.dump(commits, w)

        to_skip = set(ignore)

        # Filter out reverted commits
        revert_pattern = re.compile("This reverts commit ([0-9a-f]+)")
        for commit in commits:
            match = revert_pattern.search(commit.message)
            if match:
                reverted_hexsha = match.group(1)
                # If both the revert and the reverted are present, remove them
                # If the reverted isn't present, there should be a new JIRA to track the revert
                if reverted_hexsha in [c.hexsha for c in commits]:
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
            # Fixup information overrides commit message
            fix = fixups.get(commit.hexsha)

            # A single commit can containing multiple JIRAs
            # Fixup can be either a list of JIRA keys or a single one
            jira_ids = None
            if type(fix) is list:
                jira_ids = fix
            elif type(fix) is str:
                jira_ids = [fix]

            if not jira_ids:
                # Skip reverted and merge commits
                if commit.hexsha in to_skip:
                    continue
                match = pattern.match(commit.message)
                if not match:
                    # Try to detect a revert
                    match = revert_pattern.match(commit.message)
                    if not match:
                        unidentified_commits.append(commit)
                        continue
                    # Handle the revert
                jira_ids = [match.group(0)]
            for jira_id in jira_ids:
                commits = commits_by_id.get(jira_id, [])
                commits.append(commit)
                commits_by_id[jira_id] = commits

        # Get JIRA issues for the fix version
        issues = []
        pickle_issues_name = "issues.pickle"
        if args.unpickle and os.path.exists(pickle_issues_name):
            print "Reading issue data from", pickle_issues_name
            with open(pickle_issues_name, "rb") as r:
                issues = pickle.load(r)
        else:
            jira = get_jira()
            query = """project in (HADOOP, MAPREDUCE, HDFS, YARN) and fixVersion in ("%s") and resolution=Fixed""" % (args.fix_version,)
            for i in jira_query(jira, query):
                issues.append(PickleIssue(i))
        if args.pickle:
            print "Writing issue data to", pickle_issues_name
            with open(pickle_issues_name, "wb") as w:
                pickle.dump(issues, w)
        issues_by_id = {}
        for k,v in fixups.iteritems():
            if type(v) is str:
                v = [v]
            for key in v:
                issues_by_id[key] = None
        for issue in issues:
            issues_by_id[issue.key] = issue

        issues_missing_commits = []
        for issue in issues:
            if issue.key not in commits_by_id and issue.key not in ignore_jiras:
                issues_missing_commits.append(issue)
        commits_missing_issues = []
        for key, commit in commits_by_id.iteritems():
            if key not in issues_by_id:
                commits_missing_issues.append((key, commit))

        num_issues = 0
        print "Number commits in skip list:", len(to_skip)
        print "Number identified commits:", len(commits_by_id)
        print "Number issues with matching commit(s):", len(issues_by_id)
        print "Number unidentified commits:", len(unidentified_commits)
        num_issues += len(unidentified_commits)
        for commit in unidentified_commits:
            print "\t", commit.hexsha, commit.message.encode("utf-8")
        print "Number issues with missing commits:", len(issues_missing_commits)
        num_issues += len(issues_missing_commits)
        for issue in issues_missing_commits:
            print "\t", issue.key
        print "Number commits with missing issues:", len(commits_missing_issues)
        num_issues += len(commits_missing_issues)
        for key, commits in commits_missing_issues:
            for commit in commits:
                print "\t", key, commit.hexsha, commit.message.encode("utf-8")

        if num_issues > 0:
            return 1
        return 0


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
