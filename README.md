Script for doing bulk updates of fix versions. This provides functionality that is not available via JIRA bulk updates, like updating JIRAs across multiple projects in one shot, as well as targeting custom JIRA queries.

JIRA username and password are passed via these environment variables:

    JIRA_USER=your_user_name
    JIRA_PASSWORD=your_password

By default, this script does not write any updates. The "--force" option is required to actually update JIRA.

It's heavily recommended to use the "--output" flag to log changes to an external file.
This provides a degree of safety if a JIRA update goes awry.
