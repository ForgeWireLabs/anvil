"""ForgeWire Anvil public package.

ForgeWire Anvil is the local-first planning ledger for human and agentic work.
The package is under active extraction from the ForgeWire monorepo. The names
re-exported here are the current developer-preview surface: the domain
vocabulary (enums and constants), the entity models, the workflow contract, the
wire (de)serialization helpers, the exception hierarchy, the provider and
storage protocols, the built-in provider and JSON store, the relation
migrations, data-directory resolution, and the :class:`Anvil` service facade.

Start with :class:`Anvil`::

    from forgewire_anvil import Anvil

    anvil = Anvil()                      # user-scoped dir, honors ANVIL_DATA_DIR
    await anvil.provider.create_project(key="PF", name="Platform")

Errors are raised, not wrapped: every failure is an
:class:`IssueTrackerError` subclass carrying a stable ``error_code``. The same
surface is available from the shell as the ``anvil`` command.
"""

from __future__ import annotations

from .enums import (
    BoardType,
    EventKind,
    IssueLinkTargetType,
    IssuePriority,
    IssueStatus,
    IssueType,
    LinkType,
    SprintState,
    TYPED_LINK_SECRET_FREE_FIELDS,
    TYPED_LINK_UI_SAFE_FIELDS,
)
from .exceptions import (
    BoardNotFoundError,
    InvalidTransitionError,
    IssueNotFoundError,
    IssueTrackerError,
    ProjectExistsError,
    ProjectNotFoundError,
    SprintNotFoundError,
    ValidationError,
)
from .models import (
    Board,
    Comment,
    Issue,
    IssueEvent,
    IssueLink,
    IssueRelation,
    IssueWorkItemLink,
    Project,
    SearchResult,
    Sprint,
    TypedIssueLink,
    User,
)
from .migrations import (
    merge_relation_records,
    migrate_issue_payloads,
    migrate_issue_relations,
)
from .paths import DATA_DIR_ENV_VAR, default_data_dir, resolve_data_dir
from .protocols import IssueStore, IssueTrackerProvider
from .provider import AnvilProvider
from .service import EXPORT_VERSION, Anvil, validate_bundle
from .store import SCHEMA_VERSION, AnvilStore
from .serialization import (
    board_from_dict,
    board_to_dict,
    comment_from_dict,
    comment_to_dict,
    issue_event_from_dict,
    issue_event_to_dict,
    issue_from_dict,
    issue_link_from_dict,
    issue_link_to_dict,
    issue_relation_from_dict,
    issue_relation_to_dict,
    issue_to_dict,
    project_from_dict,
    project_to_dict,
    sprint_from_dict,
    sprint_to_dict,
    typed_issue_link_from_dict,
    typed_issue_link_to_dict,
    user_from_dict,
    user_to_dict,
)
from .workflows import DEFAULT_WORKFLOW, Transition

__version__ = "0.1.0a0"

__all__ = [
    "__version__",
    # Enums and vocabulary constants
    "BoardType",
    "EventKind",
    "IssueLinkTargetType",
    "IssuePriority",
    "IssueStatus",
    "IssueType",
    "LinkType",
    "SprintState",
    "TYPED_LINK_SECRET_FREE_FIELDS",
    "TYPED_LINK_UI_SAFE_FIELDS",
    # Workflow
    "DEFAULT_WORKFLOW",
    "Transition",
    # Entities
    "Board",
    "Comment",
    "Issue",
    "IssueEvent",
    "IssueLink",
    "IssueRelation",
    "IssueWorkItemLink",
    "Project",
    "SearchResult",
    "Sprint",
    "TypedIssueLink",
    "User",
    # Protocols
    "IssueStore",
    "IssueTrackerProvider",
    # Service facade
    "Anvil",
    "EXPORT_VERSION",
    "validate_bundle",
    # Providers
    "AnvilProvider",
    # Stores
    "AnvilStore",
    "SCHEMA_VERSION",
    # Data directory
    "DATA_DIR_ENV_VAR",
    "default_data_dir",
    "resolve_data_dir",
    # Migrations
    "merge_relation_records",
    "migrate_issue_payloads",
    "migrate_issue_relations",
    # Exceptions
    "BoardNotFoundError",
    "InvalidTransitionError",
    "IssueNotFoundError",
    "IssueTrackerError",
    "ProjectExistsError",
    "ProjectNotFoundError",
    "SprintNotFoundError",
    "ValidationError",
    # Serialization
    "board_from_dict",
    "board_to_dict",
    "comment_from_dict",
    "comment_to_dict",
    "issue_event_from_dict",
    "issue_event_to_dict",
    "issue_from_dict",
    "issue_link_from_dict",
    "issue_link_to_dict",
    "issue_relation_from_dict",
    "issue_relation_to_dict",
    "issue_to_dict",
    "project_from_dict",
    "project_to_dict",
    "sprint_from_dict",
    "sprint_to_dict",
    "typed_issue_link_from_dict",
    "typed_issue_link_to_dict",
    "user_from_dict",
    "user_to_dict",
]
