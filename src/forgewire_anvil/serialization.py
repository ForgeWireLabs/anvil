"""Wire (de)serialization for ForgeWire Anvil domain models.

The ``*_to_dict`` / ``*_from_dict`` functions define the Anvil JSON storage
contract. The wire values they read and write must round-trip existing Anvil
data without loss; the ``*_from_dict`` readers keep legacy field compatibility
(for example ``typed_links`` and the former ``display_label`` name).
"""

from __future__ import annotations

from typing import Any

from .enums import (
    EventKind,
    IssueLinkTargetType,
    IssuePriority,
    IssueStatus,
    IssueType,
    LinkType,
    SprintState,
)
from .models import (
    Board,
    BoardType,
    Comment,
    Issue,
    IssueEvent,
    IssueLink,
    IssueRelation,
    IssueWorkItemLink,
    Project,
    Sprint,
    TypedIssueLink,
    User,
    _new_id,
)
from .workflows import DEFAULT_WORKFLOW


def user_to_dict(u: User | None) -> dict[str, Any] | None:
    if u is None:
        return None
    return {"id": u.id, "display_name": u.display_name, "email": u.email}


def user_from_dict(d: dict[str, Any] | None) -> User | None:
    if not d:
        return None
    return User(id=d["id"], display_name=d["display_name"], email=d.get("email"))


def comment_to_dict(c: Comment) -> dict[str, Any]:
    return {
        "id": c.id,
        "author": user_to_dict(c.author),
        "body": c.body,
        "created": c.created,
        "updated": c.updated,
    }


def comment_from_dict(d: dict[str, Any]) -> Comment:
    return Comment(
        id=d["id"],
        author=user_from_dict(d.get("author")),
        body=d.get("body", ""),
        created=d.get("created", ""),
        updated=d.get("updated"),
    )


def issue_link_to_dict(lnk: IssueLink) -> dict[str, Any]:
    return {
        "id": lnk.id,
        "link_type": lnk.link_type,
        "source_key": lnk.source_key,
        "target_key": lnk.target_key,
        "created": lnk.created,
    }


def issue_link_from_dict(d: dict[str, Any]) -> IssueLink:
    return IssueLink(
        id=d.get("id", _new_id()),
        link_type=d.get("link_type", LinkType.RELATES_TO),
        source_key=d.get("source_key", ""),
        target_key=d.get("target_key", ""),
        created=d.get("created", ""),
    )


def issue_relation_to_dict(relation: IssueRelation) -> dict[str, Any]:
    return {
        "id": relation.id,
        "source_key": relation.source_key,
        "target_type": relation.target_type,
        "target_id": relation.target_id,
        "target_label": relation.target_label,
        "url": relation.url,
        "metadata": relation.metadata,
        "created": relation.created,
    }


def issue_relation_from_dict(d: dict[str, Any]) -> IssueWorkItemLink:
    return IssueWorkItemLink(
        id=d.get("id", _new_id()),
        source_key=d.get("source_key", ""),
        target_type=d.get("target_type", IssueLinkTargetType.FABRIC_TASK),
        target_id=d.get("target_id", ""),
        target_label=d.get("target_label", d.get("display_label")),
        url=d.get("url"),
        metadata=d.get("metadata", {}),
        created=d.get("created", ""),
    )


def typed_issue_link_to_dict(lnk: IssueRelation) -> dict[str, Any]:
    return issue_relation_to_dict(lnk)


def typed_issue_link_from_dict(d: dict[str, Any]) -> TypedIssueLink:
    relation = issue_relation_from_dict(d)
    return TypedIssueLink(
        id=relation.id,
        source_key=relation.source_key,
        target_type=relation.target_type,
        target_id=relation.target_id,
        target_label=relation.target_label,
        url=relation.url,
        metadata=relation.metadata,
        created=relation.created,
    )


def issue_event_to_dict(ev: IssueEvent) -> dict[str, Any]:
    return {
        "id": ev.id,
        "kind": ev.kind,
        "timestamp": ev.timestamp,
        "actor": user_to_dict(ev.actor),
        "field_name": ev.field_name,
        "old_value": ev.old_value,
        "new_value": ev.new_value,
        "detail": ev.detail,
    }


def issue_event_from_dict(d: dict[str, Any]) -> IssueEvent:
    return IssueEvent(
        id=d.get("id", _new_id()),
        kind=d.get("kind", EventKind.UPDATED),
        timestamp=d.get("timestamp", ""),
        actor=user_from_dict(d.get("actor")),
        field_name=d.get("field_name"),
        old_value=d.get("old_value"),
        new_value=d.get("new_value"),
        detail=d.get("detail"),
    )


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "key": issue.key,
        "project_key": issue.project_key,
        "summary": issue.summary,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "issue_type": issue.issue_type,
        "assignee": user_to_dict(issue.assignee),
        "reporter": user_to_dict(issue.reporter),
        "labels": issue.labels,
        "components": issue.components,
        "parent_key": issue.parent_key,
        "sprint_id": issue.sprint_id,
        "story_points": issue.story_points,
        "due_date": issue.due_date,
        "custom_fields": issue.custom_fields,
        "comments": [comment_to_dict(c) for c in issue.comments],
        "links": [issue_link_to_dict(lnk) for lnk in issue.links],
        "relations": [
            issue_relation_to_dict(relation) for relation in issue.relations
        ],
        "typed_links": [typed_issue_link_to_dict(lnk) for lnk in issue.typed_links],
        "activity_log": [issue_event_to_dict(ev) for ev in issue.activity_log],
        "created": issue.created,
        "updated": issue.updated,
    }


def issue_from_dict(d: dict[str, Any]) -> Issue:
    return Issue(
        id=d.get("id", _new_id()),
        key=d.get("key", ""),
        project_key=d.get("project_key", ""),
        summary=d.get("summary", ""),
        description=d.get("description"),
        status=d.get("status", IssueStatus.BACKLOG),
        priority=d.get("priority", IssuePriority.MEDIUM),
        issue_type=d.get("issue_type", IssueType.TASK),
        assignee=user_from_dict(d.get("assignee")),
        reporter=user_from_dict(d.get("reporter")),
        labels=d.get("labels", []),
        components=d.get("components", []),
        parent_key=d.get("parent_key"),
        sprint_id=d.get("sprint_id"),
        story_points=d.get("story_points"),
        due_date=d.get("due_date"),
        custom_fields=d.get("custom_fields", {}),
        comments=[comment_from_dict(c) for c in d.get("comments", [])],
        links=[issue_link_from_dict(lnk) for lnk in d.get("links", [])],
        relations=[
            issue_relation_from_dict(relation) for relation in d.get("relations", [])
        ],
        typed_links=[
            typed_issue_link_from_dict(lnk) for lnk in d.get("typed_links", [])
        ],
        activity_log=[issue_event_from_dict(ev) for ev in d.get("activity_log", [])],
        created=d.get("created", ""),
        updated=d.get("updated", ""),
    )


def sprint_to_dict(s: Sprint) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "state": s.state,
        "start_date": s.start_date,
        "end_date": s.end_date,
        "goal": s.goal,
    }


def sprint_from_dict(d: dict[str, Any]) -> Sprint:
    return Sprint(
        id=d.get("id", _new_id()),
        name=d.get("name", ""),
        state=d.get("state", SprintState.FUTURE),
        start_date=d.get("start_date"),
        end_date=d.get("end_date"),
        goal=d.get("goal"),
    )


def board_to_dict(b: Board) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "board_type": b.board_type,
        "project_key": b.project_key,
        "columns": b.columns,
        "sprints": [sprint_to_dict(s) for s in b.sprints],
    }


def board_from_dict(d: dict[str, Any]) -> Board:
    return Board(
        id=d.get("id", _new_id()),
        name=d.get("name", ""),
        board_type=d.get("board_type", BoardType.KANBAN),
        project_key=d.get("project_key", ""),
        columns=d.get("columns", []),
        sprints=[sprint_from_dict(s) for s in d.get("sprints", [])],
    )


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "key": p.key,
        "name": p.name,
        "description": p.description,
        "lead": user_to_dict(p.lead),
        "issue_types": p.issue_types,
        "workflow": p.workflow,
        "created": p.created,
        "_next_issue_number": p._next_issue_number,
    }


def project_from_dict(d: dict[str, Any]) -> Project:
    proj = Project(
        key=d.get("key", ""),
        name=d.get("name", ""),
        description=d.get("description"),
        lead=user_from_dict(d.get("lead")),
        issue_types=d.get("issue_types", []),
        workflow=d.get("workflow", dict(DEFAULT_WORKFLOW)),
        created=d.get("created", ""),
    )
    proj._next_issue_number = d.get("_next_issue_number", 1)
    return proj
