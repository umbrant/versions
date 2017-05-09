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

Note though that there is not a one-to-one correspondence between git log and JIRA. This can be due to typos in git commit messages, but also from things like reverts, branch merges, or umbrella JIRAs that do not have a corresponding commit.

To support this, users can specify additional metadata via a YAML file in the `metadata/` directory. This metadata file also specifies the start and end refs for a particular JIRA fix version.


        {
            "start_ref": "5db80ea9bc872f9fa585b5a50846a95e5a3c2af4", # Mandatory
            "end_ref": "", # Optional
            "fixups": {
                # map of hash -> JIRA ID
                "539ef5aa2e872f9fa585b5a50846a95e5a3c2af4" : "HDFS-11596",
            },
            "ignore": [
                # List of hashes to ignore, e.g. addendum commits, merges
                "a8f0cdaa2e872f9fa585b5a50846a95e5a3c2af4",
            ],
            "ignore_jiras": [
                # Fixed JIRAs to ignore, like umbrella JIRAs
                "HADOOP-10105",
            ],
        }


## update

TODO: this is currently hardcoded to update JIRAs that are committed for 3.0.0-alpha1 but only marked for 2.x fix versions.

Do bulk updates of fix versions. This provides functionality that is not available via JIRA bulk updates, like updating JIRAs across multiple projects in one shot, as well as targeting custom JIRA queries.

By default, this does not write any updates. The "--force" option is required to actually update JIRA.

It's heavily recommended to use the "--output" flag to log changes to an external file.
This provides a degree of safety if a JIRA update goes awry.
