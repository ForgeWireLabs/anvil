"""Behavioral contract tests for the extracted Anvil domain core.

These pin the wire values, defaults, workflow, and (de)serialization behavior
that existing ForgeWire Anvil data depends on. The extraction must preserve
them exactly; a change here is a change to the storage contract.
"""

from __future__ import annotations

import json

import pytest

import forgewire_anvil as fa
from forgewire_anvil import serialization


# ---------------------------------------------------------------------------
# Enum wire values
# ---------------------------------------------------------------------------


def test_enum_wire_values_are_stable() -> None:
    assert [s.value for s in fa.IssueStatus] == [
        "backlog", "todo", "in_progress", "in_review", "done", "cancelled",
    ]
    assert [p.value for p in fa.IssuePriority] == [
        "lowest", "low", "medium", "high", "critical",
    ]
    assert [t.value for t in fa.IssueType] == ["epic", "story", "task", "bug", "subtask"]
    assert [b.value for b in fa.BoardType] == ["kanban", "scrum"]
    assert [s.value for s in fa.SprintState] == ["future", "active", "closed"]
    assert [k.value for k in fa.EventKind] == [
        "created", "updated", "transitioned", "commented", "linked",
        "unlinked", "assigned", "labeled", "fabric_progress",
    ]
    assert [t.value for t in fa.IssueLinkTargetType] == [
        "fabric_task", "task_service_task", "job",
        "conversation", "document", "external_jira",
    ]


def test_link_type_wire_values_are_stable() -> None:
    assert [lt.value for lt in fa.LinkType] == [
        "blocks", "is_blocked_by", "relates_to", "duplicates",
        "is_duplicated_by", "clones", "is_cloned_by",
    ]


def test_enums_are_str_subclasses() -> None:
    # str-enums so they serialize to their string value via json.dumps.
    assert isinstance(fa.IssueStatus.BACKLOG, str)
    assert json.dumps(fa.IssueStatus.DONE) == '"done"'


def test_typed_link_field_safety_constants() -> None:
    assert "metadata" not in fa.TYPED_LINK_UI_SAFE_FIELDS
    assert "metadata" in fa.TYPED_LINK_SECRET_FREE_FIELDS
    assert "source_key" in fa.TYPED_LINK_UI_SAFE_FIELDS


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_issue_defaults() -> None:
    issue = fa.Issue()
    assert issue.status == fa.IssueStatus.BACKLOG == "backlog"
    assert issue.priority == fa.IssuePriority.MEDIUM == "medium"
    assert issue.issue_type == fa.IssueType.TASK == "task"
    assert issue.id  # a uuid was generated
    assert issue.labels == [] and issue.custom_fields == {}


def test_relation_defaults() -> None:
    relation = fa.IssueRelation(source_key="PROJ-1", target_id="task-9")
    assert relation.target_type == fa.IssueLinkTargetType.FABRIC_TASK == "fabric_task"
    assert relation.metadata == {}
    assert relation.id


def test_board_default_columns_and_project_workflow() -> None:
    assert fa.Board().columns == ["backlog", "todo", "in_progress", "in_review", "done"]
    # Each Project gets its own copy of the default workflow.
    p1, p2 = fa.Project(), fa.Project()
    assert p1.workflow == fa.DEFAULT_WORKFLOW
    assert p1.workflow is not p2.workflow


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def test_default_workflow_transitions() -> None:
    wf = fa.DEFAULT_WORKFLOW
    assert wf[fa.IssueStatus.BACKLOG] == [fa.IssueStatus.TODO, fa.IssueStatus.CANCELLED]
    assert wf[fa.IssueStatus.IN_PROGRESS] == [
        fa.IssueStatus.IN_REVIEW, fa.IssueStatus.TODO, fa.IssueStatus.CANCELLED,
    ]
    assert wf[fa.IssueStatus.DONE] == []
    assert wf[fa.IssueStatus.CANCELLED] == [fa.IssueStatus.BACKLOG]


def test_transition_shape() -> None:
    t = fa.Transition(id="t1", name="Start", from_status="todo", to_status="in_progress")
    assert (t.from_status, t.to_status) == ("todo", "in_progress")


# ---------------------------------------------------------------------------
# Serialization round trips (wire fidelity)
# ---------------------------------------------------------------------------


def _populated_issue() -> fa.Issue:
    user = fa.User(id="u1", display_name="Ada", email="ada@example.com")
    return fa.Issue(
        id="i1",
        key="PROJ-42",
        project_key="PROJ",
        summary="Do the thing",
        description="details",
        status=fa.IssueStatus.IN_PROGRESS,
        priority=fa.IssuePriority.HIGH,
        issue_type=fa.IssueType.STORY,
        assignee=user,
        reporter=user,
        labels=["a", "b"],
        components=["core"],
        story_points=3.0,
        custom_fields={"team": "anvil"},
        comments=[fa.Comment(id="c1", author=user, body="hi", created="2026-01-01T00:00:00Z")],
        links=[fa.IssueLink(id="l1", link_type=fa.LinkType.BLOCKS, source_key="PROJ-42", target_key="PROJ-7")],
        relations=[fa.IssueWorkItemLink(id="r1", source_key="PROJ-42", target_type=fa.IssueLinkTargetType.JOB, target_id="job-3")],
        typed_links=[fa.IssueWorkItemLink(id="tl1", source_key="PROJ-42", target_type=fa.IssueLinkTargetType.DOCUMENT, target_id="doc-1")],
        activity_log=[fa.IssueEvent(id="e1", kind=fa.EventKind.CREATED, timestamp="2026-01-01T00:00:00Z")],
        created="2026-01-01T00:00:00Z",
        updated="2026-01-02T00:00:00Z",
    )


def test_issue_round_trips_through_json() -> None:
    issue = _populated_issue()
    # Full trip through an actual JSON string pins wire-level fidelity.
    wire = json.loads(json.dumps(fa.issue_to_dict(issue)))
    restored = fa.issue_from_dict(wire)

    assert restored.key == "PROJ-42"
    assert restored.status == "in_progress"
    assert restored.priority == "high"
    assert restored.issue_type == "story"
    assert restored.assignee.display_name == "Ada"
    assert restored.labels == ["a", "b"]
    assert restored.custom_fields == {"team": "anvil"}
    assert restored.comments[0].body == "hi"
    assert restored.links[0].link_type == "blocks"
    assert restored.relations[0].target_id == "job-3"
    assert restored.typed_links[0].target_id == "doc-1"
    assert restored.activity_log[0].kind == "created"
    assert restored.created == "2026-01-01T00:00:00Z"


def test_serialization_module_and_toplevel_are_the_same_functions() -> None:
    # serialization.py is a real module, not a duplicate implementation.
    assert serialization.issue_to_dict is fa.issue_to_dict
    assert serialization.project_from_dict is fa.project_from_dict


def test_project_round_trip_preserves_next_issue_number() -> None:
    proj = fa.Project(key="PF", name="Platform")
    proj._next_issue_number = 17
    restored = fa.project_from_dict(json.loads(json.dumps(fa.project_to_dict(proj))))
    assert restored.key == "PF"
    assert restored._next_issue_number == 17


# ---------------------------------------------------------------------------
# Legacy / missing / unknown field behavior
# ---------------------------------------------------------------------------


def test_issue_from_dict_applies_defaults_for_missing_fields() -> None:
    issue = fa.issue_from_dict({"key": "PROJ-1"})
    assert issue.key == "PROJ-1"
    assert issue.status == "backlog"
    assert issue.priority == "medium"
    assert issue.comments == [] and issue.relations == []


def test_issue_from_dict_ignores_unknown_top_level_fields() -> None:
    # Unknown top-level keys are not retained on the model; custom_fields is the
    # documented escape hatch for extension data.
    issue = fa.issue_from_dict({"key": "PROJ-1", "not_a_real_field": "x"})
    assert not hasattr(issue, "not_a_real_field")


def test_relation_reader_accepts_legacy_display_label() -> None:
    # Older typed-link records used display_label; it maps onto target_label.
    relation = fa.issue_relation_from_dict(
        {"source_key": "PROJ-1", "target_type": "document", "target_id": "d1", "display_label": "Spec"}
    )
    assert relation.target_label == "Spec"


def test_typed_issue_link_display_label_compat() -> None:
    link = fa.TypedIssueLink(source_key="PROJ-1", target_id="d1", display_label="Spec")
    assert link.display_label == "Spec"
    assert link.target_label == "Spec"
    link.display_label = "Updated"
    assert link.target_label == "Updated"


def test_relations_and_typed_links_are_independent() -> None:
    issue = fa.Issue(
        key="PROJ-1",
        relations=[fa.IssueWorkItemLink(source_key="PROJ-1", target_id="job-1", target_type=fa.IssueLinkTargetType.JOB)],
        typed_links=[fa.IssueWorkItemLink(source_key="PROJ-1", target_id="doc-1", target_type=fa.IssueLinkTargetType.DOCUMENT)],
    )
    restored = fa.issue_from_dict(json.loads(json.dumps(fa.issue_to_dict(issue))))
    assert [r.target_id for r in restored.relations] == ["job-1"]
    assert [t.target_id for t in restored.typed_links] == ["doc-1"]


# ---------------------------------------------------------------------------
# Protocol and exceptions
# ---------------------------------------------------------------------------


def test_provider_protocol_is_runtime_checkable() -> None:
    # runtime_checkable: isinstance works and a bare object is not a provider.
    assert not isinstance(object(), fa.IssueTrackerProvider)


class _InMemoryStore:
    """Minimal structural implementation of the IssueStore contract."""

    def __init__(self) -> None:
        self._projects: dict[str, fa.Project] = {}

    async def save_project(self, project: fa.Project) -> None:
        self._projects[project.key] = project

    async def load_project(self, key: str) -> fa.Project | None:
        return self._projects.get(key)

    async def delete_project(self, key: str) -> None:
        self._projects.pop(key, None)

    async def list_project_keys(self) -> list[str]:
        return sorted(self._projects)

    async def save_issues(self, project_key: str, issues: list[fa.Issue]) -> None:
        ...

    async def load_issues(self, project_key: str) -> list[fa.Issue]:
        return []

    async def save_boards(self, project_key: str, boards: list[fa.Board]) -> None:
        ...

    async def load_boards(self, project_key: str) -> list[fa.Board]:
        return []


def test_issue_store_protocol_is_runtime_checkable() -> None:
    # A bare object is not a store; a class with the full method set is.
    assert not isinstance(object(), fa.IssueStore)
    assert isinstance(_InMemoryStore(), fa.IssueStore)


def test_issue_store_protocol_covers_the_persistence_surface() -> None:
    # The abstract contract names exactly the persistence operations a concrete
    # backend (JSON store today, SQLite later) must provide.
    expected = {
        "save_project", "load_project", "delete_project", "list_project_keys",
        "save_issues", "load_issues", "save_boards", "load_boards",
    }
    members = {name for name in dir(fa.IssueStore) if not name.startswith("_")}
    assert expected <= members


@pytest.mark.parametrize(
    "exc, code",
    [
        (fa.ProjectNotFoundError("PF"), "PROJECT_NOT_FOUND"),
        (fa.ProjectExistsError("PF"), "PROJECT_EXISTS"),
        (fa.IssueNotFoundError("PF-1"), "ISSUE_NOT_FOUND"),
        (fa.InvalidTransitionError("PF-1", "done", "todo"), "INVALID_TRANSITION"),
        (fa.BoardNotFoundError("b1"), "BOARD_NOT_FOUND"),
        (fa.SprintNotFoundError("s1"), "SPRINT_NOT_FOUND"),
        (fa.ValidationError("bad"), "VALIDATION_ERROR"),
    ],
)
def test_exception_error_codes_are_stable(exc: fa.IssueTrackerError, code: str) -> None:
    assert isinstance(exc, fa.IssueTrackerError)
    assert exc.error_code == code
