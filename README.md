# Overview

Script for validating and fixing the contents of git log and JIRA fix versions for Apache Hadoop.

# Configuration

JIRA username and password are passed via these environment variables:

    JIRA_USER=your_user_name
    JIRA_PASSWORD=your_password

# Subcommands

## validate

Validates that the contents of git log match the JIRA information for a specific fix version and branch. This command reports:

* Commits that don't have a matching JIRA
* JIRAs that don't have a matching commit
* Inconsistent reverts

Since git commit messages can be imperfect, users can specify additional metadata to correct git log via a `--fixup-commits` JSON file. The file format is as follows:

        {
            "<commit_hash>" : "<jira_id>",
            ...
        }

Some JIRAs also do not have a corresponding commit, such as umbrella JIRAs or website updates. These can be whitelisted via the `--whitelist-jiras` JSON file. The file format is as follows:

        {
        "whitelist_jiras": [
            "<jira_id>",
            ...
        }

## update

TODO: this is currently hardcoded to update JIRAs that are committed for 3.0.0-alpha1 but only marked for 2.x fix versions.

Do bulk updates of fix versions. This provides functionality that is not available via JIRA bulk updates, like updating JIRAs across multiple projects in one shot, as well as targeting custom JIRA queries.

By default, this does not write any updates. The "--force" option is required to actually update JIRA.

It's heavily recommended to use the "--output" flag to log changes to an external file.
This provides a degree of safety if a JIRA update goes awry.
