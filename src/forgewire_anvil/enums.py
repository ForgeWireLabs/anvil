"""Enumerations and vocabulary constants for the ForgeWire Anvil domain.

This is the leaf module of the domain core: it depends on nothing else in the
package, so workflow definitions, models, and serialization can all build on it
without import cycles. Every value here is part of the Anvil wire contract and
must round-trip existing stored data unchanged.
"""

from __future__ import annotations

from enum import Enum


class IssueStatus(str, Enum):
    """Built-in lifecycle statuses.  Custom workflows can extend these."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"


class IssuePriority(str, Enum):
    LOWEST = "lowest"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueType(str, Enum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"


class BoardType(str, Enum):
    KANBAN = "kanban"
    SCRUM = "scrum"


class SprintState(str, Enum):
    FUTURE = "future"
    ACTIVE = "active"
    CLOSED = "closed"


class LinkType(str, Enum):
    """Relationship between two issues.

    ``LinkType`` is intentionally limited to issue-to-issue semantics such as
    blocking, duplication, cloning, and loose relation.  Use ``IssueWorkItemLink``
    with ``IssueLinkTargetType`` for provider-neutral links from an issue to
    non-issue work or knowledge records.
    """

    BLOCKS = "blocks"
    IS_BLOCKED_BY = "is_blocked_by"
    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"
    IS_DUPLICATED_BY = "is_duplicated_by"
    CLONES = "clones"
    IS_CLONED_BY = "is_cloned_by"


class IssueLinkTargetType(str, Enum):
    """Provider-neutral typed-link targets supported in Phase 1.

    The vocabulary is deliberately substrate-neutral: values identify the
    class of target record, not the storage or external provider that produced
    it.  Providers may add adapter-specific metadata, but they must preserve
    these wire values when exchanging typed links.
    """

    FABRIC_TASK = "fabric_task"
    TASK_SERVICE_TASK = "task_service_task"
    JOB = "job"
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    EXTERNAL_JIRA = "external_jira"


class EventKind(str, Enum):
    """Types of activity log entries."""

    CREATED = "created"
    UPDATED = "updated"
    TRANSITIONED = "transitioned"
    COMMENTED = "commented"
    LINKED = "linked"
    UNLINKED = "unlinked"
    ASSIGNED = "assigned"
    LABELED = "labeled"
    FABRIC_PROGRESS = "fabric_progress"


TYPED_LINK_UI_SAFE_FIELDS: frozenset[str] = frozenset({
    "source_key",
    "target_type",
    "target_id",
    "target_label",
    "display_label",
    "url",
    "created",
})
"""Typed-link fields safe to render in UI chrome or generated comments.

``metadata`` is intentionally excluded because providers can place internal
ids, routing hints, or other operational context in that bag.  A metadata key
may be displayed only when the producing provider explicitly documents it as
public, non-sensitive presentation data.
"""

TYPED_LINK_SECRET_FREE_FIELDS: frozenset[str] = frozenset({
    "source_key",
    "target_type",
    "target_id",
    "display_label",
    "url",
    "metadata",
    "created",
})
"""Typed-link fields that must never contain credentials or other secrets.

Do not store API keys, access tokens, session cookies, passwords, private
customer data, bearer material, or signed one-time URLs in any typed-link
field.  URLs must avoid embedded credentials and secret-bearing query strings;
``metadata`` is for non-secret routing and provenance values only.
"""
