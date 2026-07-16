"""Provider-agnostic domain entities for the ForgeWire Anvil planning ledger.

These mirror common issue-tracker concepts (Project, Issue, Board, Sprint) so a
built-in provider and external adapters can share the same data shapes. The
module holds entity definitions only; enums live in :mod:`forgewire_anvil.enums`,
workflow definitions in :mod:`forgewire_anvil.workflows`, and wire (de)serialization
in :mod:`forgewire_anvil.serialization`.

ForgeWire-specific integration envelopes (for example Fabric dispatch requests
and responses) are intentionally *not* part of this package: Anvil owns planning
state, and cross-system dispatch remains with the integrating system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import (
    BoardType,
    EventKind,
    IssueLinkTargetType,
    IssuePriority,
    IssueStatus,
    IssueType,
    LinkType,
    SprintState,
)
from .workflows import DEFAULT_WORKFLOW


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class User:
    """A person or agent identity."""

    id: str
    display_name: str
    email: str | None = None


@dataclass
class Comment:
    """A comment on an issue."""

    id: str = field(default_factory=_new_id)
    author: User | None = None
    body: str = ""
    created: str = field(default_factory=_utcnow_iso)
    updated: str | None = None


@dataclass
class IssueLink:
    """A directional relationship between two issues.

    This model remains the issue-to-issue relationship contract.  It should not
    be overloaded for non-issue targets unless a future migration intentionally
    supersedes it with a broader model and updates provider/storage contracts in
    lockstep.
    """

    id: str = field(default_factory=_new_id)
    link_type: str = LinkType.RELATES_TO
    source_key: str = ""
    target_key: str = ""
    created: str = field(default_factory=_utcnow_iso)


@dataclass
class IssueRelation:
    """A typed, provider-neutral relation from an issue to a work-object target.

    This is the complete Phase 1 relation contract rather than a dispatch or
    mirroring implementation.  It gives providers and stores a first-class
    shape for linking issue keys to known work or knowledge targets while
    intentionally avoiding integration-specific implementation imports.

    Required contract fields for every relation:

    - ``source_key``: source issue key, for example ``"PROJ-42"``.
    - ``target_type``: one of ``IssueLinkTargetType``.
    - ``target_id``: target identifier or provider key.
    - ``target_label``: optional human-friendly label.
    - ``url``: optional non-secret URL suitable for navigation.
    - ``metadata``: provider-neutral or provider-specific non-secret metadata.
    - ``created``: ISO-8601 creation timestamp.

    UI/comment safety contract:

    - Safe by default: ``source_key``, ``target_type``, ``target_id``,
      ``target_label``, ``url``, and ``created``.
    - Not safe by default: ``metadata``.  Individual metadata keys require an
      explicit provider contract before display.
    - No field may contain secrets, credentials, bearer tokens, session cookies,
      passwords, signed one-time URLs, or private customer payloads.
    """

    id: str = field(default_factory=_new_id)
    source_key: str = ""
    target_type: str = IssueLinkTargetType.FABRIC_TASK
    target_id: str = ""
    target_label: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=_utcnow_iso)


class IssueWorkItemLink(IssueRelation):
    """Provider-neutral link from an issue to an internal/external work object.

    ``Issue.links`` is reserved for issue-to-issue relationships represented by
    ``IssueLink``.  ``Issue.relations`` uses this model for cross-surface
    issue-to-work-object links such as tasks, jobs, conversations, documents, or
    external issue-provider records.
    """


class TypedIssueLink(IssueWorkItemLink):
    """Backward-compatible issue-relation name used by existing callers."""

    def __init__(
        self,
        id: str | None = None,
        source_key: str = "",
        target_type: str = IssueLinkTargetType.FABRIC_TASK,
        target_id: str = "",
        target_label: str | None = None,
        display_label: str | None = None,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
        created: str | None = None,
    ) -> None:
        super().__init__(
            id=id or _new_id(),
            source_key=source_key,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label if target_label is not None else display_label,
            url=url,
            metadata=metadata or {},
            created=created or _utcnow_iso(),
        )

    @property
    def display_label(self) -> str | None:
        """Compatibility accessor for callers that used the former field name."""

        return self.target_label

    @display_label.setter
    def display_label(self, value: str | None) -> None:
        self.target_label = value


@dataclass
class IssueEvent:
    """An auditable activity-log entry on an issue."""

    id: str = field(default_factory=_new_id)
    kind: str = EventKind.UPDATED
    timestamp: str = field(default_factory=_utcnow_iso)
    actor: User | None = None
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    detail: str | None = None


@dataclass
class Issue:
    """A single unit of work – the core issue tracker entity.

    Relationship fields are intentionally split by target surface:

    - ``links`` contains issue-to-issue relationships only.
    - ``relations`` contains provider-neutral issue-to-external/internal
      work-object links.

    ``typed_links`` remains as a compatibility field for callers that adopted
    the earlier typed-link name.
    """

    id: str = field(default_factory=_new_id)
    key: str = ""          # e.g. "PROJ-42"
    project_key: str = ""
    summary: str = ""
    description: str | None = None
    status: str = IssueStatus.BACKLOG
    priority: str = IssuePriority.MEDIUM
    issue_type: str = IssueType.TASK
    assignee: User | None = None
    reporter: User | None = None
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    parent_key: str | None = None          # epic link or subtask parent
    sprint_id: str | None = None
    story_points: float | None = None
    due_date: str | None = None            # ISO-8601 date or datetime
    custom_fields: dict[str, Any] = field(default_factory=dict)
    comments: list[Comment] = field(default_factory=list)
    links: list[IssueLink] = field(default_factory=list)
    relations: list[IssueWorkItemLink] = field(default_factory=list)
    typed_links: list[IssueWorkItemLink] = field(default_factory=list)
    activity_log: list[IssueEvent] = field(default_factory=list)
    created: str = field(default_factory=_utcnow_iso)
    updated: str = field(default_factory=_utcnow_iso)


@dataclass
class Sprint:
    """A time-boxed iteration."""

    id: str = field(default_factory=_new_id)
    name: str = ""
    state: str = SprintState.FUTURE
    start_date: str | None = None
    end_date: str | None = None
    goal: str | None = None


@dataclass
class Board:
    """A kanban or scrum board for a project."""

    id: str = field(default_factory=_new_id)
    name: str = ""
    board_type: str = BoardType.KANBAN
    project_key: str = ""
    columns: list[str] = field(default_factory=lambda: [
        IssueStatus.BACKLOG,
        IssueStatus.TODO,
        IssueStatus.IN_PROGRESS,
        IssueStatus.IN_REVIEW,
        IssueStatus.DONE,
    ])
    sprints: list[Sprint] = field(default_factory=list)


@dataclass
class Project:
    """A container for issues, boards, and sprints."""

    key: str = ""          # short uppercase key, e.g. "PF"
    name: str = ""
    description: str | None = None
    lead: User | None = None
    issue_types: list[str] = field(default_factory=lambda: [
        IssueType.EPIC,
        IssueType.STORY,
        IssueType.TASK,
        IssueType.BUG,
        IssueType.SUBTASK,
    ])
    workflow: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_WORKFLOW))
    created: str = field(default_factory=_utcnow_iso)

    # Runtime counters (not persisted as separate field – derived from issues)
    _next_issue_number: int = field(default=1, repr=False)


@dataclass
class SearchResult:
    """Paginated issue search result."""

    issues: list[Issue]
    total: int
    offset: int = 0
    limit: int = 50
