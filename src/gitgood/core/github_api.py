"""Simulated GitHub API operations."""

from typing import Optional

from .models import CommandResult, PRStatus, PullRequest
from .repository import VirtualRepository


class SimulatedGitHub:
    """
    Simulates GitHub operations like creating PRs, requesting reviews,
    and merging via the web interface.
    """

    def __init__(self, repo: VirtualRepository):
        self.repo = repo

    def create_pull_request(
        self,
        title: str,
        body: str,
        source: Optional[str] = None,
        target: str = "main",
    ) -> CommandResult:
        """Create a new pull request."""
        source_branch = source or self.repo.state.head

        if source_branch not in self.repo.state.branches:
            return CommandResult(
                success=False,
                message=f"error: branch '{source_branch}' does not exist",
            )

        if source_branch == target:
            return CommandResult(
                success=False,
                message="error: cannot create PR from a branch to itself",
            )

        # Check if branch is pushed
        remote_name = f"origin/{source_branch}"
        if remote_name not in self.repo.state.remote_branches:
            return CommandResult(
                success=False,
                message=f"error: branch '{source_branch}' has not been pushed to remote",
                hints=["Push your branch first: git push -u origin " + source_branch],
            )

        pr_number = self.repo.state.next_pr_number
        self.repo.state.next_pr_number += 1

        pr = PullRequest(
            number=pr_number,
            title=title,
            body=body,
            source_branch=source_branch,
            target_branch=target,
        )
        self.repo.state.pull_requests[pr_number] = pr

        output = f"""
Creating pull request for {source_branch} into {target} in learner/my-project

https://github.com/learner/my-project/pull/{pr_number}
""".strip()

        return CommandResult(success=True, output=output)

    def list_pull_requests(self, state: str = "open") -> CommandResult:
        """List pull requests."""
        prs = []
        for pr in self.repo.state.pull_requests.values():
            if state == "all" or pr.status.value == state:
                prs.append(pr)

        if not prs:
            return CommandResult(
                success=True,
                output="No pull requests match your search",
            )

        lines = []
        for pr in prs:
            status_icon = {
                PRStatus.OPEN: "O",
                PRStatus.MERGED: "M",
                PRStatus.CLOSED: "C",
            }.get(pr.status, "?")

            approved = " [APPROVED]" if pr.approved else ""
            lines.append(f"#{pr.number}  [{status_icon}]  {pr.title}{approved}")
            lines.append(f"       {pr.source_branch} -> {pr.target_branch}")

        return CommandResult(success=True, output="\n".join(lines))

    def merge_pull_request(
        self,
        pr_number: int,
        method: str = "merge",
    ) -> CommandResult:
        """Merge a pull request."""
        if pr_number not in self.repo.state.pull_requests:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} not found",
            )

        pr = self.repo.state.pull_requests[pr_number]

        if pr.status != PRStatus.OPEN:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} is already {pr.status.value}",
            )

        # Perform the merge in the virtual repo
        self.repo.checkout(pr.target_branch)
        self.repo.merge(pr.source_branch)

        pr.status = PRStatus.MERGED

        method_text = {
            "merge": "Merged",
            "squash": "Squashed and merged",
            "rebase": "Rebased and merged",
        }.get(method, "Merged")

        return CommandResult(
            success=True,
            output=f"{method_text} pull request #{pr_number} ({pr.title})",
        )

    def close_pull_request(self, pr_number: int) -> CommandResult:
        """Close a pull request without merging."""
        if pr_number not in self.repo.state.pull_requests:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} not found",
            )

        pr = self.repo.state.pull_requests[pr_number]

        if pr.status != PRStatus.OPEN:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} is already {pr.status.value}",
            )

        pr.status = PRStatus.CLOSED

        return CommandResult(
            success=True,
            output=f"Closed pull request #{pr_number}",
        )

    def request_review(self, pr_number: int, reviewers: list[str]) -> CommandResult:
        """Request reviews on a PR."""
        if pr_number not in self.repo.state.pull_requests:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} not found",
            )

        pr = self.repo.state.pull_requests[pr_number]

        for reviewer in reviewers:
            pr.reviews.append({
                "reviewer": reviewer,
                "status": "pending",
                "comment": "",
            })

        return CommandResult(
            success=True,
            output=f"Requested review from: {', '.join(reviewers)}",
        )

    def add_review(
        self,
        pr_number: int,
        reviewer: str,
        status: str,
        comment: str = "",
    ) -> CommandResult:
        """Add a review to a PR (simulates teammate review)."""
        if pr_number not in self.repo.state.pull_requests:
            return CommandResult(
                success=False,
                message=f"error: pull request #{pr_number} not found",
            )

        pr = self.repo.state.pull_requests[pr_number]

        # Update or add review
        found = False
        for review in pr.reviews:
            if review["reviewer"] == reviewer:
                review["status"] = status
                review["comment"] = comment
                found = True
                break

        if not found:
            pr.reviews.append({
                "reviewer": reviewer,
                "status": status,
                "comment": comment,
            })

        if status == "approved":
            pr.approved = True

        status_text = {
            "approved": "approved these changes",
            "request_changes": "requested changes",
            "comment": "commented",
        }.get(status, status)

        output = f"{reviewer} {status_text}"
        if comment:
            output += f"\n\n{comment}"

        return CommandResult(success=True, output=output)
