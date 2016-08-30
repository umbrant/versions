#!/bin/bash
set -e
for jira in $(cat $1 | cut -d" " -f 1 | sort -u); do
    if [[ -z $(git --no-pager log --grep "^[ \t]*$jira" -E) ]]; then
        echo $jira
    fi
done
