"""Workflow definitions for the ForgeWire Anvil domain.

Depends only on :mod:`forgewire_anvil.enums`, so the domain models can import
``DEFAULT_WORKFLOW`` for their default factories without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import IssueStatus


@dataclass(frozen=True)
class Transition:
    """An available workflow transition."""

    id: str
    name: str
    from_status: str
    to_status: str


# Default workflow: which statuses can transition to which.
DEFAULT_WORKFLOW: dict[str, list[str]] = {
    IssueStatus.BACKLOG: [IssueStatus.TODO, IssueStatus.CANCELLED],
    IssueStatus.TODO: [IssueStatus.IN_PROGRESS, IssueStatus.CANCELLED],
    IssueStatus.IN_PROGRESS: [IssueStatus.IN_REVIEW, IssueStatus.TODO, IssueStatus.CANCELLED],
    IssueStatus.IN_REVIEW: [IssueStatus.DONE, IssueStatus.IN_PROGRESS, IssueStatus.CANCELLED],
    IssueStatus.DONE: [],
    IssueStatus.CANCELLED: [IssueStatus.BACKLOG],
}
