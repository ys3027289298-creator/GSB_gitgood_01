"""Supported command definitions."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandSpec:
    """Specification for a parseable command."""
    name: str
    description: str
    usage: str
    subcommand: Optional[str] = None
    required_args: list[str] = field(default_factory=list)
    optional_args: list[str] = field(default_factory=list)
    flags: dict[str, str] = field(default_factory=dict)


# Git commands supported by the simulator
GIT_COMMANDS = {
    "init": CommandSpec(
        name="init",
        description="Create an empty Git repository",
        usage="git init",
    ),
    "status": CommandSpec(
        name="status",
        description="Show the working tree status",
        usage="git status",
    ),
    "add": CommandSpec(
        name="add",
        description="Add file contents to the index (staging area)",
        usage="git add <file>... | git add . | git add -A",
        required_args=["files"],
        flags={
            "-A": "Add all changes",
            "--all": "Add all changes",
        },
    ),
    "commit": CommandSpec(
        name="commit",
        description="Record changes to the repository",
        usage="git commit -m '<message>'",
        flags={
            "-m": "Commit message (required)",
            "-a": "Stage all modified files and commit",
            "--amend": "Amend the previous commit",
        },
    ),
    "branch": CommandSpec(
        name="branch",
        description="List, create, or delete branches",
        usage="git branch [<name>] | git branch -d <name>",
        optional_args=["name"],
        flags={
            "-d": "Delete a branch",
            "-D": "Force delete a branch",
            "-a": "List all branches (local and remote)",
            "-r": "List remote branches",
        },
    ),
    "checkout": CommandSpec(
        name="checkout",
        description="Switch branches or restore working tree files",
        usage="git checkout <branch> | git checkout -b <new-branch>",
        optional_args=["target"],
        flags={
            "-b": "Create and switch to a new branch",
            "--branch": "Create and switch to a new branch",
        },
    ),
    "switch": CommandSpec(
        name="switch",
        description="Switch branches (modern alternative to checkout)",
        usage="git switch <branch> | git switch -c <new-branch>",
        optional_args=["target"],
        flags={
            "-c": "Create and switch to a new branch",
            "--create": "Create and switch to a new branch",
        },
    ),
    "merge": CommandSpec(
        name="merge",
        description="Join two or more development histories together",
        usage="git merge <branch>",
        required_args=["branch"],
        flags={
            "--no-ff": "Create a merge commit even for fast-forward",
        },
    ),
    "log": CommandSpec(
        name="log",
        description="Show commit logs",
        usage="git log [--oneline] [-n <number>]",
        flags={
            "--oneline": "Show abbreviated commits",
            "-n": "Limit number of commits shown",
        },
    ),
    "push": CommandSpec(
        name="push",
        description="Update remote refs along with associated objects",
        usage="git push [-u] [<remote>] [<branch>]",
        optional_args=["remote", "branch"],
        flags={
            "-u": "Set upstream tracking reference",
            "--set-upstream": "Set upstream tracking reference",
        },
    ),
    "pull": CommandSpec(
        name="pull",
        description="Fetch from and integrate with another repository",
        usage="git pull [<remote>] [<branch>]",
        optional_args=["remote", "branch"],
    ),
    "fetch": CommandSpec(
        name="fetch",
        description="Download objects and refs from another repository",
        usage="git fetch [<remote>]",
        optional_args=["remote"],
    ),
    "remote": CommandSpec(
        name="remote",
        description="Manage set of tracked repositories",
        usage="git remote [-v] | git remote add <name> <url>",
        flags={
            "-v": "Show remote URL after name",
        },
    ),
    "diff": CommandSpec(
        name="diff",
        description="Show changes between commits, commit and working tree, etc",
        usage="git diff [--staged]",
        flags={
            "--staged": "Show staged changes",
            "--cached": "Show staged changes",
        },
    ),
    "reset": CommandSpec(
        name="reset",
        description="Reset current HEAD to the specified state",
        usage="git reset [<file>] | git reset --hard",
        optional_args=["file"],
        flags={
            "--hard": "Reset working directory and staging area",
            "--soft": "Reset only HEAD pointer",
        },
    ),
}

# GitHub CLI commands
GH_COMMANDS = {
    ("pr", "create"): CommandSpec(
        name="pr",
        subcommand="create",
        description="Create a pull request",
        usage="gh pr create --title '<title>' --body '<body>'",
        flags={
            "-t": "PR title",
            "--title": "PR title",
            "-b": "PR body",
            "--body": "PR body",
            "--base": "Base branch to merge into",
        },
    ),
    ("pr", "list"): CommandSpec(
        name="pr",
        subcommand="list",
        description="List pull requests",
        usage="gh pr list [--state <state>]",
        flags={
            "--state": "Filter by state (open, closed, merged, all)",
        },
    ),
    ("pr", "merge"): CommandSpec(
        name="pr",
        subcommand="merge",
        description="Merge a pull request",
        usage="gh pr merge [<number>] [--merge|--squash|--rebase]",
        optional_args=["number"],
        flags={
            "--merge": "Use merge commit",
            "--squash": "Squash commits before merging",
            "--rebase": "Rebase commits before merging",
        },
    ),
    ("pr", "close"): CommandSpec(
        name="pr",
        subcommand="close",
        description="Close a pull request",
        usage="gh pr close <number>",
        required_args=["number"],
    ),
    ("pr", "view"): CommandSpec(
        name="pr",
        subcommand="view",
        description="View a pull request",
        usage="gh pr view [<number>]",
        optional_args=["number"],
    ),
}


def get_command_help(cmd_type: str, command: str, subcommand: str = None) -> str:
    """Get help text for a command."""
    if cmd_type == "git":
        spec = GIT_COMMANDS.get(command)
    else:
        spec = GH_COMMANDS.get((command, subcommand))

    if not spec:
        return f"Unknown command: {command}"

    lines = [
        f"{spec.description}",
        "",
        f"Usage: {spec.usage}",
    ]

    if spec.flags:
        lines.append("")
        lines.append("Flags:")
        for flag, desc in spec.flags.items():
            lines.append(f"  {flag:20} {desc}")

    return "\n".join(lines)
