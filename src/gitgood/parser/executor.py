"""Command execution and routing."""

from typing import Optional

from ..core.models import CommandResult
from ..core.repository import VirtualRepository
from ..core.github_api import SimulatedGitHub
from .lexer import ParsedCommand, ParseError
from .commands import GIT_COMMANDS, GH_COMMANDS, get_command_help


class CommandExecutor:
    """Routes parsed commands to the appropriate simulator methods."""

    def __init__(self, repo: VirtualRepository, github: SimulatedGitHub):
        self.repo = repo
        self.github = github

    def execute(self, cmd: ParsedCommand) -> CommandResult:
        """Execute a parsed command and return the result."""
        if cmd.command_type == "internal":
            return self._handle_internal(cmd)
        elif cmd.command_type == "git":
            return self._handle_git(cmd)
        elif cmd.command_type == "gh":
            return self._handle_gh(cmd)

        return CommandResult(
            success=False,
            message=f"Unknown command type: {cmd.command_type}",
        )

    def _handle_internal(self, cmd: ParsedCommand) -> CommandResult:
        """Handle internal commands."""
        if cmd.command == "help":
            if cmd.args:
                return CommandResult(
                    success=True,
                    output=get_command_help("git", cmd.args[0]),
                )
            return CommandResult(
                success=True,
                output=self._get_general_help(),
            )

        if cmd.command in ("quit", "exit"):
            return CommandResult(
                success=True,
                message="__EXIT__",
            )

        return CommandResult(
            success=True,
            message=f"Internal command: {cmd.command}",
        )

    def _handle_git(self, cmd: ParsedCommand) -> CommandResult:
        """Handle git commands."""
        handlers = {
            "status": self._git_status,
            "add": self._git_add,
            "commit": self._git_commit,
            "branch": self._git_branch,
            "checkout": self._git_checkout,
            "switch": self._git_switch,
            "merge": self._git_merge,
            "log": self._git_log,
            "push": self._git_push,
            "pull": self._git_pull,
            "fetch": self._git_fetch,
            "diff": self._git_diff,
            "remote": self._git_remote,
        }

        handler = handlers.get(cmd.command)
        if not handler:
            if cmd.command in GIT_COMMANDS:
                return CommandResult(
                    success=False,
                    message=f"git {cmd.command}: not yet implemented in simulation",
                )
            return CommandResult(
                success=False,
                message=f"git: '{cmd.command}' is not a git command",
                hints=["Type 'help' to see available commands"],
            )

        return handler(cmd)

    def _handle_gh(self, cmd: ParsedCommand) -> CommandResult:
        """Handle GitHub CLI commands."""
        if cmd.command != "pr":
            return CommandResult(
                success=False,
                message=f"gh: '{cmd.command}' is not supported. Only 'gh pr' commands are available.",
            )

        handlers = {
            "create": self._gh_pr_create,
            "list": self._gh_pr_list,
            "merge": self._gh_pr_merge,
            "close": self._gh_pr_close,
            "view": self._gh_pr_view,
        }

        handler = handlers.get(cmd.subcommand)
        if not handler:
            return CommandResult(
                success=False,
                message=f"gh pr: '{cmd.subcommand}' is not a valid subcommand",
                hints=["Available: create, list, merge, close, view"],
            )

        return handler(cmd)

    # Git command handlers

    def _git_status(self, cmd: ParsedCommand) -> CommandResult:
        return self.repo.get_status_output()

    def _git_add(self, cmd: ParsedCommand) -> CommandResult:
        if "-A" in cmd.flags or "--all" in cmd.flags:
            return self.repo.add_file("-A")

        if not cmd.args:
            return CommandResult(
                success=False,
                message="Nothing specified, nothing added.",
                hints=["Use 'git add <file>' or 'git add .' to stage files"],
            )

        for filename in cmd.args:
            result = self.repo.add_file(filename)
            if not result.success:
                return result

        return CommandResult(success=True, message="")

    def _git_commit(self, cmd: ParsedCommand) -> CommandResult:
        message = cmd.flags.get("-m") or cmd.flags.get("--message")
        if not message:
            return CommandResult(
                success=False,
                message="error: switch 'm' requires a value",
                hints=["Usage: git commit -m 'Your commit message'"],
            )

        add_all = "-a" in cmd.flags
        return self.repo.commit(message, add_all=add_all)

    def _git_branch(self, cmd: ParsedCommand) -> CommandResult:
        # Delete branch
        if "-d" in cmd.flags or "-D" in cmd.flags:
            branch_name = cmd.flags.get("-d") or cmd.flags.get("-D") or (cmd.args[0] if cmd.args else None)
            if not branch_name:
                return CommandResult(
                    success=False,
                    message="error: branch name required",
                )
            force = "-D" in cmd.flags
            return self.repo.delete_branch(branch_name, force=force)

        # List branches
        if not cmd.args:
            all_branches = "-a" in cmd.flags or "--all" in cmd.flags
            return self.repo.list_branches(all_branches=all_branches)

        # Create branch
        return self.repo.create_branch(cmd.args[0])

    def _git_checkout(self, cmd: ParsedCommand) -> CommandResult:
        create = "-b" in cmd.flags or "--branch" in cmd.flags

        if create:
            branch_name = cmd.flags.get("-b") or cmd.flags.get("--branch")
            if not branch_name and cmd.args:
                branch_name = cmd.args[0]

            if not branch_name:
                return CommandResult(
                    success=False,
                    message="error: switch 'b' requires a value",
                    hints=["Usage: git checkout -b <branch-name>"],
                )
            return self.repo.checkout(branch_name, create=True)

        if not cmd.args:
            return CommandResult(
                success=False,
                message="error: you must specify a branch to checkout",
                hints=["Usage: git checkout <branch-name>"],
            )

        return self.repo.checkout(cmd.args[0])

    def _git_switch(self, cmd: ParsedCommand) -> CommandResult:
        create = "-c" in cmd.flags or "--create" in cmd.flags

        if create:
            branch_name = cmd.flags.get("-c") or cmd.flags.get("--create")
            if not branch_name and cmd.args:
                branch_name = cmd.args[0]

            if not branch_name:
                return CommandResult(
                    success=False,
                    message="error: switch 'c' requires a value",
                    hints=["Usage: git switch -c <branch-name>"],
                )
            return self.repo.checkout(branch_name, create=True)

        if not cmd.args:
            return CommandResult(
                success=False,
                message="error: missing branch name",
            )

        return self.repo.checkout(cmd.args[0])

    def _git_merge(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult(
                success=False,
                message="error: specify a branch to merge",
            )

        no_ff = "--no-ff" in cmd.flags
        return self.repo.merge(cmd.args[0], no_ff=no_ff)

    def _git_log(self, cmd: ParsedCommand) -> CommandResult:
        oneline = "--oneline" in cmd.flags
        count = 10

        if "-n" in cmd.flags and cmd.flags["-n"]:
            try:
                count = int(cmd.flags["-n"])
            except ValueError:
                pass

        return self.repo.get_log(count=count, oneline=oneline)

    def _git_push(self, cmd: ParsedCommand) -> CommandResult:
        remote = "origin"
        branch = None
        set_upstream = "-u" in cmd.flags or "--set-upstream" in cmd.flags

        # Handle -u flag potentially consuming the remote name as its value
        # -u/--set-upstream is a boolean flag, so any value it has is actually the remote
        if set_upstream:
            flag_value = cmd.flags.get("-u") or cmd.flags.get("--set-upstream")
            if flag_value:
                # The flag consumed what should be the remote name
                remote = flag_value
                if cmd.args:
                    branch = cmd.args[0]
            elif cmd.args:
                remote = cmd.args[0]
                if len(cmd.args) > 1:
                    branch = cmd.args[1]
        elif cmd.args:
            remote = cmd.args[0]
            if len(cmd.args) > 1:
                branch = cmd.args[1]

        return self.repo.push(remote=remote, branch=branch, set_upstream=set_upstream)

    def _git_pull(self, cmd: ParsedCommand) -> CommandResult:
        remote = cmd.args[0] if cmd.args else "origin"
        branch = cmd.args[1] if len(cmd.args) > 1 else None
        return self.repo.pull(remote=remote, branch=branch)

    def _git_fetch(self, cmd: ParsedCommand) -> CommandResult:
        remote = cmd.args[0] if cmd.args else "origin"
        return self.repo.fetch(remote=remote)

    def _git_diff(self, cmd: ParsedCommand) -> CommandResult:
        staged = "--staged" in cmd.flags or "--cached" in cmd.flags

        if staged:
            if self.repo.state.staged_changes:
                lines = []
                for change in self.repo.state.staged_changes:
                    lines.append(f"diff --git a/{change.filename} b/{change.filename}")
                    lines.append(f"--- a/{change.filename}")
                    lines.append(f"+++ b/{change.filename}")
                    lines.append("@@ -1,1 +1,1 @@")
                    lines.append("+simulated change")
                return CommandResult(success=True, output="\n".join(lines))
            return CommandResult(success=True, output="")

        if self.repo.state.working_changes:
            lines = []
            for filename in self.repo.state.working_changes:
                lines.append(f"diff --git a/{filename} b/{filename}")
                lines.append(f"--- a/{filename}")
                lines.append(f"+++ b/{filename}")
                lines.append("@@ -1,1 +1,1 @@")
                lines.append("+simulated change")
            return CommandResult(success=True, output="\n".join(lines))

        return CommandResult(success=True, output="")

    def _git_remote(self, cmd: ParsedCommand) -> CommandResult:
        if "-v" in cmd.flags:
            url = self.repo.state.remote_url or "https://github.com/learner/my-project.git"
            return CommandResult(
                success=True,
                output=f"origin  {url} (fetch)\norigin  {url} (push)",
            )

        return CommandResult(
            success=True,
            output="origin",
        )

    # GitHub CLI handlers

    def _gh_pr_create(self, cmd: ParsedCommand) -> CommandResult:
        title = cmd.flags.get("-t") or cmd.flags.get("--title")
        body = cmd.flags.get("-b") or cmd.flags.get("--body") or ""
        base = cmd.flags.get("--base") or "main"

        if not title:
            return CommandResult(
                success=False,
                message="error: --title is required",
                hints=["Usage: gh pr create --title 'PR Title' --body 'Description'"],
            )

        return self.github.create_pull_request(
            title=title,
            body=body,
            target=base,
        )

    def _gh_pr_list(self, cmd: ParsedCommand) -> CommandResult:
        state = cmd.flags.get("--state") or "open"
        return self.github.list_pull_requests(state=state)

    def _gh_pr_merge(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            # Find open PR for current branch
            current = self.repo.state.head
            for pr in self.repo.state.pull_requests.values():
                if pr.source_branch == current and pr.status.value == "open":
                    pr_number = pr.number
                    break
            else:
                return CommandResult(
                    success=False,
                    message="error: no open pull request for current branch",
                )
        else:
            try:
                pr_number = int(cmd.args[0])
            except ValueError:
                return CommandResult(
                    success=False,
                    message="error: invalid PR number",
                )

        method = "merge"
        if "--squash" in cmd.flags:
            method = "squash"
        elif "--rebase" in cmd.flags:
            method = "rebase"

        return self.github.merge_pull_request(pr_number, method=method)

    def _gh_pr_close(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult(
                success=False,
                message="error: PR number required",
            )

        try:
            pr_number = int(cmd.args[0])
        except ValueError:
            return CommandResult(
                success=False,
                message="error: invalid PR number",
            )

        return self.github.close_pull_request(pr_number)

    def _gh_pr_view(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            # Find PR for current branch
            current = self.repo.state.head
            for pr in self.repo.state.pull_requests.values():
                if pr.source_branch == current:
                    pr_number = pr.number
                    break
            else:
                return CommandResult(
                    success=False,
                    message="no pull request found for current branch",
                )
        else:
            try:
                pr_number = int(cmd.args[0])
            except ValueError:
                return CommandResult(
                    success=False,
                    message="error: invalid PR number",
                )

        if pr_number not in self.repo.state.pull_requests:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} not found",
            )

        pr = self.repo.state.pull_requests[pr_number]
        lines = [
            f"#{pr.number}: {pr.title}",
            f"  Status: {pr.status.value.upper()}",
            f"  {pr.source_branch} -> {pr.target_branch}",
            "",
            pr.body or "(No description)",
        ]

        if pr.reviews:
            lines.append("")
            lines.append("Reviews:")
            for review in pr.reviews:
                lines.append(f"  - {review['reviewer']}: {review['status']}")

        return CommandResult(success=True, output="\n".join(lines))

    def _get_general_help(self) -> str:
        return """
GitHub Flow Learning Tool - Available Commands

Git Commands:
  git status              Show working tree status
  git add <file>          Stage files for commit
  git commit -m 'msg'     Create a commit
  git branch              List branches
  git checkout -b <name>  Create and switch to branch
  git checkout <branch>   Switch to existing branch
  git push -u origin <b>  Push branch to remote
  git pull                Pull changes from remote
  git merge <branch>      Merge a branch
  git log                 Show commit history

GitHub CLI:
  gh pr create            Create a pull request
  gh pr list              List pull requests
  gh pr merge             Merge a pull request
  gh pr view              View pull request details

App Commands:
  help [command]          Show help for a command
  lesson                  Show current lesson
  lessons                 List all lessons
  hint                    Get a hint for current step
  quit                    Exit the application
""".strip()
