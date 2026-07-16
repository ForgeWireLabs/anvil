"""Behavioral tests for the extracted Anvil provider.

These mirror the ForgeWire suite that exercises the in-repo provider
(tests/jira/test_local_issue_tracker.py) so the standalone package proves the
same behavior on its own, outside the application import tree. The provider
body is byte-identical to the extracted source; these tests pin the behavior
that must survive the extraction.

The service-layer cases from the ForgeWire suite are intentionally absent:
IssueTrackerService and its OperationResult wrapping are ForgeWire integration
concerns, not part of the standalone package.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import forgewire_anvil as fa
from forgewire_anvil.provider import AnvilProvider
from forgewire_anvil.store import AnvilStore


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def store(tmp_path: Path) -> AnvilStore:
    return AnvilStore(root=str(tmp_path / "issue_tracker"))


@pytest.fixture()
def provider(store: AnvilStore) -> AnvilProvider:
    return AnvilProvider(store)


# ---------------------------------------------------------------------------
# Construction / protocol
# ---------------------------------------------------------------------------


def test_provider_satisfies_protocol(provider: AnvilProvider) -> None:
    assert isinstance(provider, fa.IssueTrackerProvider)


def test_provider_defaults_to_its_own_store() -> None:
    assert isinstance(AnvilProvider()._store, AnvilStore)


def test_close_is_a_noop(provider: AnvilProvider) -> None:
    run(provider.close())


# ---------------------------------------------------------------------------
# Project lifecycle
# ---------------------------------------------------------------------------


def test_create_and_get_project(provider: AnvilProvider) -> None:
    project = run(provider.create_project(key="DEMO", name="Demo Project"))
    assert project.key == "DEMO"
    assert project.name == "Demo Project"
    # Lookup is case-insensitive.
    assert run(provider.get_project("demo")).key == "DEMO"


def test_create_duplicate_project_raises(provider: AnvilProvider) -> None:
    run(provider.create_project(key="DUP", name="First"))
    with pytest.raises(fa.ProjectExistsError):
        run(provider.create_project(key="dup", name="Second"))


def test_list_projects(provider: AnvilProvider) -> None:
    run(provider.create_project(key="A", name="Alpha"))
    run(provider.create_project(key="B", name="Bravo"))
    assert {p.key for p in run(provider.list_projects())} == {"A", "B"}


def test_delete_project(provider: AnvilProvider) -> None:
    run(provider.create_project(key="DEL", name="To Delete"))
    run(provider.delete_project("DEL"))
    with pytest.raises(fa.ProjectNotFoundError):
        run(provider.get_project("DEL"))


def test_delete_nonexistent_project_raises(provider: AnvilProvider) -> None:
    with pytest.raises(fa.ProjectNotFoundError):
        run(provider.delete_project("NOPE"))


def test_empty_project_key_raises(provider: AnvilProvider) -> None:
    with pytest.raises(fa.ValidationError):
        run(provider.create_project(key="", name="Bad"))


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------


def test_create_issue(provider: AnvilProvider) -> None:
    run(provider.create_project(key="TST", name="Test"))
    issue = run(provider.create_issue(
        project_key="TST",
        summary="Fix the widget",
        description="It's broken",
        priority="high",
        labels=["urgent", "backend"],
    ))
    assert issue.key == "TST-1"
    assert issue.summary == "Fix the widget"
    assert issue.status == fa.IssueStatus.BACKLOG
    assert issue.labels == ["urgent", "backend"]


def test_auto_incrementing_keys(provider: AnvilProvider) -> None:
    run(provider.create_project(key="SEQ", name="Sequence"))
    keys = [
        run(provider.create_issue(project_key="SEQ", summary=s)).key
        for s in ("First", "Second", "Third")
    ]
    assert keys == ["SEQ-1", "SEQ-2", "SEQ-3"]


def test_get_issue(provider: AnvilProvider) -> None:
    run(provider.create_project(key="GET", name="Get"))
    run(provider.create_issue(project_key="GET", summary="Hello"))
    assert run(provider.get_issue("GET-1")).summary == "Hello"


def test_get_nonexistent_issue_raises(provider: AnvilProvider) -> None:
    run(provider.create_project(key="NF", name="NF"))
    with pytest.raises(fa.IssueNotFoundError):
        run(provider.get_issue("NF-999"))


def test_update_issue(provider: AnvilProvider) -> None:
    run(provider.create_project(key="UPD", name="Update"))
    run(provider.create_issue(project_key="UPD", summary="Original"))
    updated = run(provider.update_issue(
        "UPD-1", summary="Updated", priority="critical", labels=["changed"],
    ))
    assert updated.summary == "Updated"
    assert updated.priority == "critical"
    assert updated.labels == ["changed"]


def test_delete_issue(provider: AnvilProvider) -> None:
    run(provider.create_project(key="RM", name="Remove"))
    run(provider.create_issue(project_key="RM", summary="Bye"))
    run(provider.delete_issue("RM-1"))
    with pytest.raises(fa.IssueNotFoundError):
        run(provider.get_issue("RM-1"))


def test_empty_summary_raises(provider: AnvilProvider) -> None:
    run(provider.create_project(key="VAL", name="Validate"))
    with pytest.raises(fa.ValidationError):
        run(provider.create_issue(project_key="VAL", summary=""))


def test_issue_in_nonexistent_project_raises(provider: AnvilProvider) -> None:
    with pytest.raises(fa.ProjectNotFoundError):
        run(provider.create_issue(project_key="FAKE", summary="Nope"))


def test_issue_survives_a_fresh_provider_over_the_same_store(store: AnvilStore) -> None:
    """Data is durable: a second provider reads what the first wrote."""
    p1 = AnvilProvider(store)
    run(p1.create_project(key="DUR", name="Durable"))
    run(p1.create_issue(project_key="DUR", summary="Persisted"))

    p2 = AnvilProvider(store)
    assert run(p2.get_issue("DUR-1")).summary == "Persisted"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_status(provider: AnvilProvider) -> None:
    run(provider.create_project(key="S", name="Search"))
    run(provider.create_issue(project_key="S", summary="A"))
    run(provider.create_issue(project_key="S", summary="B"))
    run(provider.transition_issue("S-1", fa.IssueStatus.TODO))

    result = run(provider.search_issues(project_key="S", status=fa.IssueStatus.TODO))
    assert result.total == 1
    assert result.issues[0].key == "S-1"


def test_search_by_text_is_case_insensitive(provider: AnvilProvider) -> None:
    run(provider.create_project(key="TXT", name="Text"))
    run(provider.create_issue(project_key="TXT", summary="Login bug"))
    run(provider.create_issue(project_key="TXT", summary="Dashboard feature"))

    result = run(provider.search_issues(text="login"))
    assert result.total == 1
    assert result.issues[0].summary == "Login bug"


def test_search_by_label(provider: AnvilProvider) -> None:
    run(provider.create_project(key="LBL", name="Label"))
    run(provider.create_issue(project_key="LBL", summary="A", labels=["frontend"]))
    run(provider.create_issue(project_key="LBL", summary="B", labels=["backend"]))

    assert run(provider.search_issues(labels=["backend"])).total == 1


def test_search_across_all_projects(provider: AnvilProvider) -> None:
    run(provider.create_project(key="X", name="X"))
    run(provider.create_project(key="Y", name="Y"))
    run(provider.create_issue(project_key="X", summary="x1"))
    run(provider.create_issue(project_key="Y", summary="y1"))

    assert run(provider.search_issues()).total == 2


def test_search_pagination(provider: AnvilProvider) -> None:
    run(provider.create_project(key="PG", name="Page"))
    for n in range(5):
        run(provider.create_issue(project_key="PG", summary=f"Issue {n}"))

    page = run(provider.search_issues(project_key="PG", offset=2, limit=2))
    assert len(page.issues) == 2
    assert page.total == 5
    assert page.offset == 2


# ---------------------------------------------------------------------------
# Workflow / transitions
# ---------------------------------------------------------------------------


def test_valid_transition(provider: AnvilProvider) -> None:
    run(provider.create_project(key="WF", name="Workflow"))
    run(provider.create_issue(project_key="WF", summary="Flow"))

    assert run(provider.transition_issue("WF-1", fa.IssueStatus.TODO)).status == fa.IssueStatus.TODO
    assert run(
        provider.transition_issue("WF-1", fa.IssueStatus.IN_PROGRESS)
    ).status == fa.IssueStatus.IN_PROGRESS


def test_invalid_transition_raises(provider: AnvilProvider) -> None:
    run(provider.create_project(key="BAD", name="Bad"))
    run(provider.create_issue(project_key="BAD", summary="No"))
    # backlog -> done is not a legal edge in the default workflow.
    with pytest.raises(fa.InvalidTransitionError):
        run(provider.transition_issue("BAD-1", fa.IssueStatus.DONE))


def test_get_transitions_offers_only_legal_targets(provider: AnvilProvider) -> None:
    run(provider.create_project(key="TR", name="Trans"))
    run(provider.create_issue(project_key="TR", summary="T"))

    targets = {t.to_status for t in run(provider.get_transitions("TR-1"))}
    assert fa.IssueStatus.TODO in targets
    assert fa.IssueStatus.CANCELLED in targets
    assert fa.IssueStatus.DONE not in targets


def test_full_happy_path_workflow(provider: AnvilProvider) -> None:
    run(provider.create_project(key="FULL", name="Full"))
    run(provider.create_issue(project_key="FULL", summary="E2E"))

    issue = None
    for status in (fa.IssueStatus.TODO, fa.IssueStatus.IN_PROGRESS,
                   fa.IssueStatus.IN_REVIEW, fa.IssueStatus.DONE):
        issue = run(provider.transition_issue("FULL-1", status))
    assert issue is not None
    assert issue.status == fa.IssueStatus.DONE


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_add_comment(provider: AnvilProvider) -> None:
    run(provider.create_project(key="CMT", name="Comment"))
    run(provider.create_issue(project_key="CMT", summary="C"))

    author = fa.User(id="u1", display_name="Alice")
    comment = run(provider.add_comment("CMT-1", "Looks good!", author=author))
    assert comment.body == "Looks good!"
    assert comment.author is not None
    assert comment.author.display_name == "Alice"

    assert len(run(provider.get_issue("CMT-1")).comments) == 1


def test_comment_on_nonexistent_issue_raises(provider: AnvilProvider) -> None:
    run(provider.create_project(key="NC", name="NC"))
    with pytest.raises(fa.IssueNotFoundError):
        run(provider.add_comment("NC-999", "Ghost"))


# ---------------------------------------------------------------------------
# Boards and sprints
# ---------------------------------------------------------------------------


def test_default_board_created_with_project(provider: AnvilProvider) -> None:
    run(provider.create_project(key="BD", name="Board"))
    boards = run(provider.list_boards(project_key="BD"))
    assert len(boards) == 1
    assert boards[0].project_key == "BD"


def test_get_board(provider: AnvilProvider) -> None:
    run(provider.create_project(key="GB", name="GetBoard"))
    boards = run(provider.list_boards(project_key="GB"))
    assert run(provider.get_board(boards[0].id)).name == "GetBoard Board"


def test_get_nonexistent_board_raises(provider: AnvilProvider) -> None:
    with pytest.raises(fa.BoardNotFoundError):
        run(provider.get_board("no-such-board"))


def test_create_start_and_close_sprint(provider: AnvilProvider) -> None:
    run(provider.create_project(key="SP", name="Sprint"))
    board_id = run(provider.list_boards(project_key="SP"))[0].id

    sprint = run(provider.create_sprint(board_id=board_id, name="Sprint 1", goal="Ship MVP"))
    assert sprint.name == "Sprint 1"
    assert sprint.state == fa.SprintState.FUTURE

    sprint = run(provider.start_sprint(sprint.id))
    assert sprint.state == fa.SprintState.ACTIVE
    assert sprint.start_date is not None

    sprint = run(provider.close_sprint(sprint.id))
    assert sprint.state == fa.SprintState.CLOSED
    assert sprint.end_date is not None


# ---------------------------------------------------------------------------
# Typed relations — the dual-field (relations / typed_links) write behavior
# ---------------------------------------------------------------------------


def _seed_issue(provider: AnvilProvider, key: str = "REL") -> None:
    run(provider.create_project(key=key, name="Relations"))
    run(provider.create_issue(project_key=key, summary="Source"))


def test_add_relation_writes_both_relation_fields(provider: AnvilProvider) -> None:
    """A relation is recorded on relations and mirrored on typed_links."""
    _seed_issue(provider)
    added = run(provider.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1",
        target_type=fa.IssueLinkTargetType.FABRIC_TASK,
        target_id="task-1",
    )))

    issue = run(provider.get_issue("REL-1"))
    assert [r.id for r in issue.relations] == [added.id]
    assert [r.id for r in issue.typed_links] == [added.id]


def test_add_relation_updates_existing_by_target(provider: AnvilProvider) -> None:
    """Re-adding the same (target_type, target_id) updates rather than
    duplicating."""
    _seed_issue(provider)
    run(provider.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1", target_type="fabric_task", target_id="task-1",
        metadata={"terminal_status": "pending"},
    )))
    run(provider.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1", target_type="fabric_task", target_id="task-1",
        metadata={"terminal_status": "running"},
    )))

    issue = run(provider.get_issue("REL-1"))
    assert len(issue.typed_links) == 1
    assert issue.typed_links[0].metadata["terminal_status"] == "running"
    assert len(issue.links) == 0  # issue-to-issue links stay separate


def test_add_relation_rejects_mismatched_source_key(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    with pytest.raises(fa.ValidationError):
        run(provider.add_relation("REL-1", fa.IssueRelation(
            source_key="OTHER-9", target_type="job", target_id="j1",
        )))


def test_add_relation_rejects_empty_target_id(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    with pytest.raises(fa.ValidationError):
        run(provider.add_relation("REL-1", fa.IssueRelation(
            source_key="REL-1", target_type="job", target_id="",
        )))


def test_add_relation_on_nonexistent_issue_raises(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    with pytest.raises(fa.IssueNotFoundError):
        run(provider.add_relation("REL-404", fa.IssueRelation(
            source_key="REL-404", target_type="job", target_id="j1",
        )))


def test_list_relations_returns_union_without_duplicates(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    added = [
        run(provider.add_relation("REL-1", fa.IssueRelation(
            source_key="REL-1", target_type=t.value, target_id=f"target-{i}",
        )))
        for i, t in enumerate(fa.IssueLinkTargetType)
    ]

    listed = run(provider.list_relations("REL-1"))
    assert {r.id for r in listed} == {r.id for r in added}
    assert len(listed) == len(added)  # union by id, no duplicates


def test_remove_relation_clears_both_fields(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    first = run(provider.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1", target_type="fabric_task", target_id="task-1",
    )))
    run(provider.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1", target_type="job", target_id="job-1",
    )))

    run(provider.remove_relation("REL-1", first.id))

    issue = run(provider.get_issue("REL-1"))
    assert first.id not in {r.id for r in issue.relations}
    assert first.id not in {r.id for r in issue.typed_links}
    assert len(issue.relations) == 1
    assert len(issue.typed_links) == 1


def test_remove_unknown_relation_raises(provider: AnvilProvider) -> None:
    _seed_issue(provider)
    with pytest.raises(fa.IssueTrackerError):
        run(provider.remove_relation("REL-1", "no-such-relation"))


def test_relations_persist_across_providers(store: AnvilStore) -> None:
    p1 = AnvilProvider(store)
    _seed_issue(p1)
    added = run(p1.add_relation("REL-1", fa.IssueRelation(
        source_key="REL-1", target_type="fabric_task", target_id="task-1",
    )))

    p2 = AnvilProvider(store)
    issue = run(p2.get_issue("REL-1"))
    assert [r.id for r in issue.relations] == [added.id]
    assert [r.id for r in issue.typed_links] == [added.id]


# ---------------------------------------------------------------------------
# Issue-to-issue links
# ---------------------------------------------------------------------------


def test_add_and_remove_issue_link(provider: AnvilProvider) -> None:
    run(provider.create_project(key="LK", name="Links"))
    run(provider.create_issue(project_key="LK", summary="One"))
    run(provider.create_issue(project_key="LK", summary="Two"))

    link = run(provider.add_link("LK-1", fa.IssueLink(
        link_type=fa.LinkType.BLOCKS, source_key="LK-1", target_key="LK-2",
    )))
    issue = run(provider.get_issue("LK-1"))
    assert [lnk.id for lnk in issue.links] == [link.id]
    # Issue-to-issue links do not leak into the typed-relation fields.
    assert issue.relations == []

    run(provider.remove_link("LK-1", link.id))
    assert run(provider.get_issue("LK-1")).links == []
