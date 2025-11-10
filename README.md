# List Github Workflows

This was written by Junie/Sonnet 4.0

Prompt:

Write a python script which uses the `gh` command-line tool to list repos in a given organization like gh repo list organization --no-archived --limit 50.

Use the git cli to do a shallow checkout of each repository.

Load each yaml workflow in .github/workflows and find all the `uses` references of external workflows.

Print a report showing what workflows each repository uses.
