#!/usr/bin/env python3
"""
Script to analyze GitHub workflows across repositories in an organization.

This script:
1. Lists repositories in a given organization using the gh CLI
2. Performs shallow checkouts of each repository
3. Parses YAML workflow files in .github/workflows
4. Extracts all 'uses' references to external workflows
5. Generates a report showing what workflows each repository uses
"""

import subprocess
import os
import shutil
import tempfile
import yaml
import argparse
from pathlib import Path
from typing import List, Dict, Set
import sys


def run_command(command: List[str], cwd: str = None) -> str:
    """Run a command and return its output."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(command)}: {e}")
        print(f"stderr: {e.stderr}")
        return ""


def list_organization_repos(org_name: str, limit: int = 50) -> List[str]:
    """List repositories in an organization using gh CLI."""
    print(f"Fetching repositories for organization: {org_name}")
    
    command = [
        "gh", "repo", "list", org_name,
        "--no-archived",
        "--limit", str(limit)
    ]
    
    output = run_command(command)
    if not output:
        return []
    
    repos = []
    for line in output.split('\n'):
        if line.strip():
            # gh repo list output format: "owner/repo-name	description	visibility"
            repo_name = line.split('\t')[0]
            repos.append(repo_name)
    
    print(f"Found {len(repos)} repositories")
    return repos


def shallow_clone_repo(repo_name: str, clone_dir: str) -> str:
    """Perform a shallow clone of a repository."""
    repo_url = f"https://github.com/{repo_name}.git"
    repo_path = os.path.join(clone_dir, repo_name.split('/')[-1])
    
    print(f"Cloning {repo_name}...")
    
    command = [
        "git", "clone", "--depth", "1",
        repo_url, repo_path
    ]
    
    result = run_command(command, cwd=clone_dir)
    if os.path.exists(repo_path):
        return repo_path
    else:
        print(f"Failed to clone {repo_name}")
        return ""


def find_workflow_files(repo_path: str) -> List[str]:
    """Find all YAML workflow files in .github/workflows directory."""
    workflows_dir = os.path.join(repo_path, ".github", "workflows")
    
    if not os.path.exists(workflows_dir):
        return []
    
    workflow_files = []
    for file in os.listdir(workflows_dir):
        if file.endswith(('.yml', '.yaml')):
            workflow_files.append(os.path.join(workflows_dir, file))
    
    return workflow_files


def extract_uses_from_workflow(workflow_file: str) -> Set[str]:
    """Extract all 'uses' references from a workflow YAML file."""
    uses_references = set()
    
    try:
        with open(workflow_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
        
        if not isinstance(content, dict):
            return uses_references
        
        # Recursively search for 'uses' keys in the YAML structure
        def find_uses(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'uses' and isinstance(value, str):
                        # Only include external actions (not local ones starting with './')
                        if not value.startswith('./'):
                            uses_references.add(value)
                    else:
                        find_uses(value)
            elif isinstance(obj, list):
                for item in obj:
                    find_uses(item)
        
        find_uses(content)
        
    except Exception as e:
        print(f"Error parsing workflow file {workflow_file}: {e}")
    
    return uses_references


def analyze_repository_workflows(repo_name: str, repo_path: str) -> Dict[str, Set[str]]:
    """Analyze all workflows in a repository and extract uses references."""
    workflow_files = find_workflow_files(repo_path)
    
    if not workflow_files:
        return {}
    
    print(f"  Found {len(workflow_files)} workflow files in {repo_name}")
    
    all_uses = {}
    
    for workflow_file in workflow_files:
        workflow_name = os.path.basename(workflow_file)
        uses_refs = extract_uses_from_workflow(workflow_file)
        
        if uses_refs:
            all_uses[workflow_name] = uses_refs
    
    return all_uses


def generate_report(results: Dict[str, Dict[str, Set[str]]]):
    """Generate and print a comprehensive report."""
    print("\n" + "="*80)
    print("WORKFLOW USAGE REPORT")
    print("="*80)
    
    # Summary statistics
    total_repos = len(results)
    repos_with_workflows = sum(1 for workflows in results.values() if workflows)
    total_workflows = sum(len(workflows) for workflows in results.values())
    
    print(f"\nSUMMARY:")
    print(f"Total repositories analyzed: {total_repos}")
    print(f"Repositories with workflows: {repos_with_workflows}")
    print(f"Total workflow files found: {total_workflows}")
    
    # Collect all unique external actions
    all_external_actions = set()
    for workflows in results.values():
        for uses_set in workflows.values():
            all_external_actions.update(uses_set)
    
    print(f"Unique external actions used: {len(all_external_actions)}")
    
    print("\n" + "-"*80)
    print("DETAILED RESULTS BY REPOSITORY:")
    print("-"*80)
    
    for repo_name in sorted(results.keys()):
        workflows = results[repo_name]
        
        if not workflows:
            print(f"\n{repo_name}: No workflows found")
            continue
        
        print(f"\n{repo_name}:")
        for workflow_name in sorted(workflows.keys()):
            uses_refs = workflows[workflow_name]
            print(f"  {workflow_name}:")
            if uses_refs:
                for use_ref in sorted(uses_refs):
                    print(f"    - {use_ref}")
            else:
                print(f"    - No external actions")
    
    # Most popular external actions
    if all_external_actions:
        print("\n" + "-"*80)
        print("MOST POPULAR EXTERNAL ACTIONS:")
        print("-"*80)
        
        action_counts = {}
        for workflows in results.values():
            for uses_set in workflows.values():
                for action in uses_set:
                    action_counts[action] = action_counts.get(action, 0) + 1
        
        # Sort by usage count (descending)
        sorted_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)
        
        for action, count in sorted_actions[:20]:  # Top 20
            print(f"{count:3d} uses: {action}")


def main():
    """Main function to orchestrate the workflow analysis."""
    parser = argparse.ArgumentParser(description='Analyze GitHub workflows across organization repositories')
    parser.add_argument('organization', help='GitHub organization name')
    parser.add_argument('--limit', type=int, default=50, help='Maximum number of repositories to analyze (default: 50)')
    
    args = parser.parse_args()
    
    # Check if required tools are available
    try:
        run_command(["gh", "--version"])
    except FileNotFoundError:
        print("Error: 'gh' command not found. Please install GitHub CLI.")
        sys.exit(1)
    
    try:
        run_command(["git", "--version"])
    except FileNotFoundError:
        print("Error: 'git' command not found. Please install Git.")
        sys.exit(1)
    
    # Create temporary directory for cloning
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Using temporary directory: {temp_dir}")
        
        # List repositories
        repos = list_organization_repos(args.organization, args.limit)
        
        if not repos:
            print("No repositories found!")
            return
        
        results = {}
        
        # Process each repository
        for i, repo_name in enumerate(repos, 1):
            print(f"\nProcessing {i}/{len(repos)}: {repo_name}")
            
            # Clone repository
            repo_path = shallow_clone_repo(repo_name, temp_dir)
            
            if repo_path:
                # Analyze workflows
                workflows = analyze_repository_workflows(repo_name, repo_path)
                results[repo_name] = workflows
            else:
                results[repo_name] = {}
        
        # Generate report
        generate_report(results)


if __name__ == "__main__":
    main()