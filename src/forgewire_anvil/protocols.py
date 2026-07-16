"""Protocol definition for Anvil issue-tracker providers.

Every planning backend (the built-in provider and any external adapter)
implements this protocol so a service layer can swap them transparently.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .models import (Board, Comment, Issue, IssueLink,
                     IssueRelation, Project, SearchResult, Sprint,
                     User)
from .workflows import Transition


@runtime_checkable
class IssueTrackerProvider(Protocol):
    """Abstract interface that every issue-tracker backend must satisfy.

    Lifecycle
    ---------
    Providers may own reusable clients/sessions (for example an HTTP session
    against Jira). Callers should invoke :meth:`close` during service shutdown
    so those transport-level resources are released deterministically.
    """

    # -- Projects -------------------------------------------------------

    async def create_project(
        self,
        *,
        key: str,
        name: str,
        description: str | None = None,
        lead: User | None = None,
        board_type: str = "kanban",
    ) -> Project: ...

    async def get_project(self, project_key: str) -> Project: ...

    async def list_projects(self) -> list[Project]: ...

    async def delete_project(self, project_key: str) -> None: ...

    # -- Issues ---------------------------------------------------------

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str | None = None,
        issue_type: str = "task",
        priority: str = "medium",
        assignee: User | None = None,
        labels: Sequence[str] | None = None,
        components: Sequence[str] | None = None,
        parent_key: str | None = None,
        sprint_id: str | None = None,
        story_points: float | None = None,
        due_date: str | None = None,
        custom_fields: Mapping[str, Any] | None = None,
    ) -> Issue: ...

    async def get_issue(self, issue_key: str) -> Issue: ...

    async def update_issue(
        self,
        issue_key: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        assignee: User | None = None,
        labels: Sequence[str] | None = None,
        components: Sequence[str] | None = None,
        sprint_id: str | None = None,
        story_points: float | None = None,
        due_date: str | None = None,
        custom_fields: Mapping[str, Any] | None = None,
    ) -> Issue: ...

    async def delete_issue(self, issue_key: str) -> None: ...

    async def search_issues(
        self,
        *,
        project_key: str | None = None,
        status: str | None = None,
        assignee_id: str | None = None,
        labels: Sequence[str] | None = None,
        text: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> SearchResult: ...

    # -- Transitions ----------------------------------------------------

    async def get_transitions(self, issue_key: str) -> list[Transition]: ...

    async def transition_issue(self, issue_key: str, to_status: str) -> Issue: ...

    # -- Comments -------------------------------------------------------

    async def add_comment(self, issue_key: str, body: str, *, author: User | None = None) -> Comment: ...

    # -- Boards ---------------------------------------------------------

    async def get_board(self, board_id: str) -> Board: ...

    async def list_boards(self, *, project_key: str | None = None) -> list[Board]: ...

    # -- Sprints --------------------------------------------------------

    async def create_sprint(
        self,
        *,
        board_id: str,
        name: str,
        start_date: str | None = None,
        end_date: str | None = None,
        goal: str | None = None,
    ) -> Sprint: ...

    async def start_sprint(self, sprint_id: str) -> Sprint: ...

    async def close_sprint(self, sprint_id: str) -> Sprint: ...

    # -- Issue-to-issue links -------------------------------------------

    async def add_link(
        self,
        issue_key: str,
        link: IssueLink,
    ) -> IssueLink: ...

    async def remove_link(
        self,
        issue_key: str,
        link_id: str,
    ) -> None: ...

    # -- Typed issue relations ------------------------------------------

    async def add_relation(
        self,
        issue_key: str,
        relation: IssueRelation,
    ) -> IssueRelation: ...

    async def remove_relation(
        self,
        issue_key: str,
        relation_id: str,
    ) -> None: ...

    async def list_relations(
        self,
        issue_key: str,
    ) -> list[IssueRelation]: ...

    async def close(self) -> None: ...


@runtime_checkable
class IssueStore(Protocol):
    """Provider-neutral persistence contract for Anvil planning data.

    A store persists projects, issues, and boards keyed by project. The
    concrete developer-preview backend is a JSON file store; a future
    multi-process backend (for example SQLite) implements this same contract so
    a provider can be pointed at either without code changes. Storage is defined
    as a protocol here in the domain core; concrete stores live in later slices
    and must preserve unknown and legacy record fields on round trip.
    """

    async def save_project(self, project: Project) -> None: ...

    async def load_project(self, key: str) -> Project | None: ...

    async def delete_project(self, key: str) -> None: ...

    async def list_project_keys(self) -> list[str]: ...

    async def save_issues(self, project_key: str, issues: list[Issue]) -> None: ...

    async def load_issues(self, project_key: str) -> list[Issue]: ...

    async def save_boards(self, project_key: str, boards: list[Board]) -> None: ...

    async def load_boards(self, project_key: str) -> list[Board]: ...
