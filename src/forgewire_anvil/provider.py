"""The built-in ForgeWire Anvil planning provider.

Implements the :class:`~forgewire_anvil.protocols.IssueTrackerProvider`
protocol on top of an :class:`~forgewire_anvil.protocols.IssueStore`
(the JSON store by default).  All the familiar tracker concepts (projects,
issues, boards, sprints, workflows) work offline with no external
dependencies and no network.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .enums import (BoardType, EventKind, IssuePriority, IssueStatus,
                    IssueType, SprintState)
from .exceptions import (BoardNotFoundError, InvalidTransitionError,
                         IssueNotFoundError, IssueTrackerError,
                         ProjectExistsError, ProjectNotFoundError,
                         SprintNotFoundError, ValidationError)
from .models import (Board, Comment, Issue, IssueEvent, IssueLink,
                     IssueRelation, Project, SearchResult, Sprint, User,
                     _new_id, _utcnow_iso)
from .store import AnvilStore
from .workflows import DEFAULT_WORKFLOW, Transition

logger = logging.getLogger(__name__)


class AnvilProvider:
    """Anvil — ForgeWire's built-in issue tracker backed by JSON files.

    Parameters
    ----------
    store:
        ``AnvilStore`` instance.  If omitted a default store writing
        to ``data/issue_tracker/`` is created.
    """

    def __init__(self, store: AnvilStore | None = None) -> None:
        self._store = store or AnvilStore()

    async def close(self) -> None:
        """No-op lifecycle hook for protocol parity.

        ``AnvilProvider`` does not keep long-lived network/database sessions,
        but the service layer calls this method uniformly during shutdown.
        """
        return

    # ==================================================================
    # Projects
    # ==================================================================

    async def create_project(
        self,
        *,
        key: str,
        name: str,
        description: str | None = None,
        lead: User | None = None,
        board_type: str = "kanban",
    ) -> Project:
        key = key.upper().strip()
        if not key:
            raise ValidationError("Project key must not be empty", field="key")
        if not key.isalnum():
            raise ValidationError("Project key must be alphanumeric", field="key")

        existing = await self._store.load_project(key)
        if existing is not None:
            raise ProjectExistsError(key)

        project = Project(
            key=key,
            name=name or key,
            description=description,
            lead=lead,
        )
        await self._store.save_project(project)

        # Create a default board
        board = Board(
            name=f"{name or key} Board",
            board_type=board_type,
            project_key=key,
        )
        await self._store.save_boards(key, [board])

        return project

    async def get_project(self, project_key: str) -> Project:
        project = await self._store.load_project(project_key.upper())
        if project is None:
            raise ProjectNotFoundError(project_key)
        return project

    async def list_projects(self) -> list[Project]:
        keys = await self._store.list_project_keys()
        projects: list[Project] = []
        for k in keys:
            p = await self._store.load_project(k)
            if p is not None:
                projects.append(p)
        return projects

    async def delete_project(self, project_key: str) -> None:
        project_key = project_key.upper()
        existing = await self._store.load_project(project_key)
        if existing is None:
            raise ProjectNotFoundError(project_key)
        await self._store.delete_project(project_key)

    # ==================================================================
    # Issues
    # ==================================================================

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
    ) -> Issue:
        project_key = project_key.upper()
        project = await self._store.load_project(project_key)
        if project is None:
            raise ProjectNotFoundError(project_key)

        if not summary or not summary.strip():
            raise ValidationError("Summary must not be empty", field="summary")

        # Allocate issue key
        issue_number = project._next_issue_number
        project._next_issue_number += 1
        await self._store.save_project(project)

        issue_key = f"{project_key}-{issue_number}"
        now = _utcnow_iso()

        issue = Issue(
            key=issue_key,
            project_key=project_key,
            summary=summary.strip(),
            description=description,
            status=IssueStatus.BACKLOG,
            priority=priority,
            issue_type=issue_type,
            assignee=assignee,
            labels=list(labels or []),
            components=list(components or []),
            parent_key=parent_key,
            sprint_id=sprint_id,
            story_points=story_points,
            due_date=due_date,
            custom_fields=dict(custom_fields or {}),
            created=now,
            updated=now,
            activity_log=[
                IssueEvent(
                    kind=EventKind.CREATED,
                    timestamp=now,
                    actor=assignee,
                    detail=f"Issue {issue_key} created",
                ),
            ],
        )

        issues = await self._store.load_issues(project_key)
        issues.append(issue)
        await self._store.save_issues(project_key, issues)

        return issue

    async def get_issue(self, issue_key: str) -> Issue:
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        for issue in issues:
            if issue.key == issue_key:
                return issue
        raise IssueNotFoundError(issue_key)

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
    ) -> Issue:
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)

        target: Issue | None = None
        for i, issue in enumerate(issues):
            if issue.key == issue_key:
                target = issue
                break

        if target is None:
            raise IssueNotFoundError(issue_key)

        if summary is not None:
            target.summary = summary.strip()
        if description is not None:
            target.description = description
        if priority is not None:
            target.priority = priority
        if assignee is not None:
            target.assignee = assignee
        if labels is not None:
            target.labels = list(labels)
        if components is not None:
            target.components = list(components)
        if sprint_id is not None:
            target.sprint_id = sprint_id
        if story_points is not None:
            target.story_points = story_points
        if due_date is not None:
            target.due_date = due_date
        if custom_fields is not None:
            target.custom_fields.update(custom_fields)

        target.updated = _utcnow_iso()
        await self._store.save_issues(project_key, issues)
        return target

    async def delete_issue(self, issue_key: str) -> None:
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        before = len(issues)
        issues = [i for i in issues if i.key != issue_key]
        if len(issues) == before:
            raise IssueNotFoundError(issue_key)
        await self._store.save_issues(project_key, issues)

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
    ) -> SearchResult:
        # Gather issues from target project(s)
        if project_key:
            all_issues = await self._store.load_issues(project_key.upper())
        else:
            all_issues = []
            for key in await self._store.list_project_keys():
                all_issues.extend(await self._store.load_issues(key))

        # Filter
        filtered = all_issues
        if status:
            filtered = [i for i in filtered if i.status == status]
        if assignee_id:
            filtered = [i for i in filtered if i.assignee and i.assignee.id == assignee_id]
        if labels:
            label_set = set(labels)
            filtered = [i for i in filtered if label_set.intersection(i.labels)]
        if text:
            text_lower = text.lower()
            filtered = [
                i for i in filtered
                if text_lower in (i.summary or "").lower()
                or text_lower in (i.description or "").lower()
            ]

        total = len(filtered)
        page = filtered[offset: offset + limit]
        return SearchResult(issues=page, total=total, offset=offset, limit=limit)

    # ==================================================================
    # Transitions / Workflow
    # ==================================================================

    async def get_transitions(self, issue_key: str) -> list[Transition]:
        issue = await self.get_issue(issue_key)
        project = await self._store.load_project(issue.project_key)
        workflow = (project.workflow if project else DEFAULT_WORKFLOW)
        targets = workflow.get(issue.status, [])
        return [
            Transition(
                id=f"{issue.status}->{t}",
                name=t.replace("_", " ").title(),
                from_status=issue.status,
                to_status=t,
            )
            for t in targets
        ]

    async def transition_issue(self, issue_key: str, to_status: str) -> Issue:
        issue = await self.get_issue(issue_key)
        project = await self._store.load_project(issue.project_key)
        workflow = (project.workflow if project else DEFAULT_WORKFLOW)
        allowed = workflow.get(issue.status, [])

        if to_status not in allowed:
            raise InvalidTransitionError(issue_key, issue.status, to_status)

        project_key = issue.project_key
        issues = await self._store.load_issues(project_key)
        for i in issues:
            if i.key == issue_key:
                old_status = i.status
                i.status = to_status
                i.updated = _utcnow_iso()
                i.activity_log.append(IssueEvent(
                    kind=EventKind.TRANSITIONED,
                    timestamp=i.updated,
                    field_name="status",
                    old_value=old_status,
                    new_value=to_status,
                    detail=f"Transitioned from {old_status} to {to_status}",
                ))
                break

        await self._store.save_issues(project_key, issues)
        return await self.get_issue(issue_key)

    # ==================================================================
    # Links
    # ==================================================================

    async def add_link(self, issue_key: str, link: IssueLink) -> IssueLink:
        """Persist a link on *issue_key* and return it with an assigned id."""
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        target: Issue | None = None
        for i in issues:
            if i.key == issue_key:
                target = i
                break
        if target is None:
            raise IssueNotFoundError(issue_key)

        # Ensure the link has an id
        if not link.id:
            link = IssueLink(
                id=_new_id(),
                link_type=link.link_type,
                target_key=link.target_key,
            )

        target.links.append(link)
        target.updated = _utcnow_iso()
        target.activity_log.append(IssueEvent(
            kind=EventKind.LINKED,
            timestamp=target.updated,
            detail=f"Linked {link.link_type} -> {link.target_key}",
        ))
        await self._store.save_issues(project_key, issues)
        return link

    async def remove_link(self, issue_key: str, link_id: str) -> None:
        """Remove a link by *link_id* from *issue_key*."""
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        target: Issue | None = None
        for i in issues:
            if i.key == issue_key:
                target = i
                break
        if target is None:
            raise IssueNotFoundError(issue_key)

        original_len = len(target.links)
        target.links = [lk for lk in target.links if lk.id != link_id]
        if len(target.links) == original_len:
            raise IssueTrackerError(f"Link {link_id!r} not found on {issue_key}")

        target.updated = _utcnow_iso()
        target.activity_log.append(IssueEvent(
            kind=EventKind.UNLINKED,
            timestamp=target.updated,
            detail=f"Removed link {link_id}",
        ))
        await self._store.save_issues(project_key, issues)

    # ==================================================================
    # Typed relations
    # ==================================================================

    async def add_relation(
        self,
        issue_key: str,
        relation: IssueRelation,
    ) -> IssueRelation:
        """Persist a typed relation on *issue_key* and return it."""
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        target: Issue | None = None
        for issue in issues:
            if issue.key == issue_key:
                target = issue
                break
        if target is None:
            raise IssueNotFoundError(issue_key)

        if not relation.id:
            relation.id = _new_id()
        if not relation.source_key:
            relation.source_key = issue_key
        if relation.source_key != issue_key:
            raise ValidationError(
                "Relation source_key must match issue_key", field="source_key"
            )
        if not relation.target_id:
            raise ValidationError(
                "Relation target_id must not be empty", field="target_id"
            )
        if not relation.created:
            relation.created = _utcnow_iso()

        existing_typed_link = next(
            (
                typed_link
                for typed_link in target.typed_links
                if typed_link.target_type == relation.target_type
                and typed_link.target_id == relation.target_id
            ),
            None,
        )

        if existing_typed_link is not None:
            existing_typed_link.source_key = relation.source_key
            existing_typed_link.target_label = relation.target_label
            existing_typed_link.url = relation.url
            existing_typed_link.metadata = dict(relation.metadata)
            relation = existing_typed_link
        else:
            target.typed_links.append(relation)

        relation_by_id = {item.id: item for item in target.relations}
        relation_by_id[relation.id] = relation
        target.relations = list(relation_by_id.values())

        target.updated = _utcnow_iso()
        target.activity_log.append(IssueEvent(
            kind=EventKind.LINKED,
            timestamp=target.updated,
            detail=(
                f"Linked relation {relation.target_type} -> "
                f"{relation.target_id}"
            ),
        ))
        await self._store.save_issues(project_key, issues)
        return relation

    async def remove_relation(self, issue_key: str, relation_id: str) -> None:
        """Remove a typed relation by *relation_id* from *issue_key*."""
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        target: Issue | None = None
        for issue in issues:
            if issue.key == issue_key:
                target = issue
                break
        if target is None:
            raise IssueNotFoundError(issue_key)

        original_len = len(target.relations) + len(target.typed_links)
        target.relations = [
            relation for relation in target.relations if relation.id != relation_id
        ]
        target.typed_links = [
            relation for relation in target.typed_links if relation.id != relation_id
        ]
        if len(target.relations) + len(target.typed_links) == original_len:
            raise IssueTrackerError(
                f"Relation {relation_id!r} not found on {issue_key}"
            )

        target.updated = _utcnow_iso()
        target.activity_log.append(IssueEvent(
            kind=EventKind.UNLINKED,
            timestamp=target.updated,
            detail=f"Removed relation {relation_id}",
        ))
        await self._store.save_issues(project_key, issues)

    async def list_relations(self, issue_key: str) -> list[IssueRelation]:
        """Return typed relations recorded for *issue_key*."""
        issue = await self.get_issue(issue_key)
        relations_by_id: dict[str, IssueRelation] = {}
        for relation in [*issue.relations, *issue.typed_links]:
            relations_by_id.setdefault(relation.id, relation)
        return list(relations_by_id.values())

    # ==================================================================
    # Comments
    # ==================================================================

    async def add_comment(
        self,
        issue_key: str,
        body: str,
        *,
        author: User | None = None,
    ) -> Comment:
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)

        comment: Comment | None = None
        for issue in issues:
            if issue.key == issue_key:
                comment = Comment(body=body, author=author)
                issue.comments.append(comment)
                issue.updated = _utcnow_iso()
                issue.activity_log.append(IssueEvent(
                    kind=EventKind.COMMENTED,
                    timestamp=issue.updated,
                    actor=author,
                    detail=f"Comment added",
                ))
                break

        if comment is None:
            raise IssueNotFoundError(issue_key)

        await self._store.save_issues(project_key, issues)
        return comment

    async def append_activity_event(self, issue_key: str, event: IssueEvent) -> IssueEvent:
        """Append an activity event to ``issue_key`` without mutating issue fields."""
        project_key = self._project_key_from_issue(issue_key)
        issues = await self._store.load_issues(project_key)
        for issue in issues:
            if issue.key == issue_key:
                issue.activity_log.append(event)
                issue.updated = _utcnow_iso()
                await self._store.save_issues(project_key, issues)
                return event
        raise IssueNotFoundError(issue_key)

    # ==================================================================
    # Boards
    # ==================================================================

    async def get_board(self, board_id: str) -> Board:
        for key in await self._store.list_project_keys():
            boards = await self._store.load_boards(key)
            for board in boards:
                if board.id == board_id:
                    return board
        raise BoardNotFoundError(board_id)

    async def list_boards(self, *, project_key: str | None = None) -> list[Board]:
        if project_key:
            return await self._store.load_boards(project_key.upper())
        result: list[Board] = []
        for key in await self._store.list_project_keys():
            result.extend(await self._store.load_boards(key))
        return result

    # ==================================================================
    # Sprints
    # ==================================================================

    async def create_sprint(
        self,
        *,
        board_id: str,
        name: str,
        start_date: str | None = None,
        end_date: str | None = None,
        goal: str | None = None,
    ) -> Sprint:
        board = await self.get_board(board_id)
        sprint = Sprint(
            name=name,
            start_date=start_date,
            end_date=end_date,
            goal=goal,
        )
        board.sprints.append(sprint)
        boards = await self._store.load_boards(board.project_key)
        for i, b in enumerate(boards):
            if b.id == board_id:
                boards[i] = board
                break
        await self._store.save_boards(board.project_key, boards)
        return sprint

    async def start_sprint(self, sprint_id: str) -> Sprint:
        return await self._update_sprint_state(sprint_id, SprintState.ACTIVE)

    async def close_sprint(self, sprint_id: str) -> Sprint:
        return await self._update_sprint_state(sprint_id, SprintState.CLOSED)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _project_key_from_issue(issue_key: str) -> str:
        """Extract project key from ``PROJ-123`` style key."""
        parts = issue_key.rsplit("-", 1)
        if len(parts) != 2:
            raise IssueNotFoundError(issue_key)
        return parts[0].upper()

    async def _update_sprint_state(self, sprint_id: str, state: str) -> Sprint:
        for key in await self._store.list_project_keys():
            boards = await self._store.load_boards(key)
            for board in boards:
                for sprint in board.sprints:
                    if sprint.id == sprint_id:
                        sprint.state = state
                        if state == SprintState.ACTIVE and not sprint.start_date:
                            sprint.start_date = _utcnow_iso()
                        if state == SprintState.CLOSED and not sprint.end_date:
                            sprint.end_date = _utcnow_iso()
                        await self._store.save_boards(key, boards)
                        return sprint
        raise SprintNotFoundError(sprint_id)
