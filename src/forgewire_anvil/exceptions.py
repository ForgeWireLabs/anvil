"""ForgeWire Anvil exception hierarchy.

These cover the planning-domain failures Anvil owns. Integration-specific
failures (for example Fabric dispatch errors) remain with the integrating
system and are intentionally not part of this package. Error-code strings are a
stable part of the contract and must not change without a compatibility plan.
"""

from __future__ import annotations


class IssueTrackerError(Exception):
    """Base exception for all Anvil planning errors."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class ProjectNotFoundError(IssueTrackerError):
    def __init__(self, project_key: str) -> None:
        super().__init__(f"Project not found: {project_key}", error_code="PROJECT_NOT_FOUND")
        self.project_key = project_key


class ProjectExistsError(IssueTrackerError):
    def __init__(self, project_key: str) -> None:
        super().__init__(f"Project already exists: {project_key}", error_code="PROJECT_EXISTS")
        self.project_key = project_key


class IssueNotFoundError(IssueTrackerError):
    def __init__(self, issue_key: str) -> None:
        super().__init__(f"Issue not found: {issue_key}", error_code="ISSUE_NOT_FOUND")
        self.issue_key = issue_key


class InvalidTransitionError(IssueTrackerError):
    def __init__(self, issue_key: str, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Cannot transition {issue_key} from '{from_status}' to '{to_status}'",
            error_code="INVALID_TRANSITION",
        )
        self.issue_key = issue_key
        self.from_status = from_status
        self.to_status = to_status


class BoardNotFoundError(IssueTrackerError):
    def __init__(self, board_id: str) -> None:
        super().__init__(f"Board not found: {board_id}", error_code="BOARD_NOT_FOUND")
        self.board_id = board_id


class SprintNotFoundError(IssueTrackerError):
    def __init__(self, sprint_id: str) -> None:
        super().__init__(f"Sprint not found: {sprint_id}", error_code="SPRINT_NOT_FOUND")
        self.sprint_id = sprint_id


class ValidationError(IssueTrackerError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, error_code="VALIDATION_ERROR")
        self.field = field
