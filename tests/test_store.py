"""Behavioral tests for the Anvil JSON store.

These pin the on-disk layout, atomic round-trip behavior, and the
unknown/legacy field preservation contract that existing ForgeWire Anvil data
depends on.

An on-disk parity test against ForgeWire's in-repo store lived here during the
extraction. It was removed once ForgeWire began consuming this package: there
is only one store implementation now, so the comparison compared the code to
itself.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import forgewire_anvil as fa
from forgewire_anvil import serialization
from forgewire_anvil.store import SCHEMA_VERSION, AnvilStore, _METADATA_FILENAME


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures — deterministic entities (fixed ids/timestamps so serialization is
# reproducible and parity comparisons are byte-for-byte).
# ---------------------------------------------------------------------------


def _project() -> fa.Project:
    return fa.Project(
        key="pf",
        name="Platform",
        description="Platform work",
        created="2026-07-15T00:00:00+00:00",
    )


def _issue(key: str = "PF-1") -> fa.Issue:
    return fa.Issue(
        id="issue-1",
        key=key,
        project_key="PF",
        summary="Build the thing",
        status=fa.IssueStatus.TODO,
        priority=fa.IssuePriority.HIGH,
        issue_type=fa.IssueType.TASK,
        comments=[fa.Comment(id="c1", body="first", created="2026-07-15T00:00:00+00:00")],
        created="2026-07-15T00:00:00+00:00",
        updated="2026-07-15T00:00:00+00:00",
    )


def _board() -> fa.Board:
    return fa.Board(id="board-1", name="Main", project_key="PF")


# ---------------------------------------------------------------------------
# Layout and round-trips
# ---------------------------------------------------------------------------


def test_project_dir_uses_uppercase_key(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(_project()))
    assert (tmp_path / "PF" / "project.json").exists()


def test_project_round_trip(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(_project()))
    loaded = run(store.load_project("PF"))
    assert loaded is not None
    # The directory is uppercased for lookup, but the project's own key field is
    # persisted verbatim — the store does not rewrite entity contents.
    assert loaded.key == "pf"
    assert loaded.name == "Platform"


def test_load_missing_project_returns_none(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    assert run(store.load_project("NOPE")) is None


def test_issues_round_trip(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_issues("PF", [_issue()]))
    loaded = run(store.load_issues("PF"))
    assert [i.key for i in loaded] == ["PF-1"]
    assert loaded[0].comments[0].body == "first"


def test_boards_round_trip(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_boards("PF", [_board()]))
    loaded = run(store.load_boards("PF"))
    assert [b.name for b in loaded] == ["Main"]


def test_load_missing_issues_and_boards_return_empty(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    assert run(store.load_issues("PF")) == []
    assert run(store.load_boards("PF")) == []


def test_list_project_keys(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(fa.Project(key="pf", name="Platform")))
    run(store.save_project(fa.Project(key="ax", name="Apex")))
    # A directory with only issues (no project.json) must not be listed.
    run(store.save_issues("zz", [_issue("ZZ-1")]))
    assert run(store.list_project_keys()) == ["AX", "PF"]


def test_delete_project_removes_directory(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(_project()))
    run(store.save_issues("PF", [_issue()]))
    run(store.delete_project("PF"))
    assert not (tmp_path / "PF").exists()
    assert run(store.list_project_keys()) == []


# ---------------------------------------------------------------------------
# Unknown / legacy field preservation and merge-by-id
# ---------------------------------------------------------------------------


def test_unknown_top_level_field_preserved_on_resave(tmp_path: Path) -> None:
    """A field the current serializer does not know about survives re-save."""
    store = AnvilStore(tmp_path)
    d = tmp_path / "PF"
    d.mkdir(parents=True)
    legacy = serialization.issue_to_dict(_issue())
    legacy["x_future_field"] = "keep-me"
    (d / "issues.json").write_text(json.dumps([legacy]))

    run(store.save_issues("PF", [_issue()]))

    raw = json.loads((d / "issues.json").read_text())
    assert raw[0]["x_future_field"] == "keep-me"


def test_nested_record_unknown_field_merged_by_id(tmp_path: Path) -> None:
    """Unknown keys on a nested record (matched by id) survive re-save."""
    store = AnvilStore(tmp_path)
    d = tmp_path / "PF"
    d.mkdir(parents=True)
    legacy = serialization.issue_to_dict(_issue())
    # Attach an unknown key onto the existing comment record (id "c1").
    legacy["comments"][0]["x_reactions"] = 3
    (d / "issues.json").write_text(json.dumps([legacy]))

    # Re-save the current issue; its comment "c1" body is updated.
    updated = _issue()
    updated.comments[0].body = "edited"
    run(store.save_issues("PF", [updated]))

    raw = json.loads((d / "issues.json").read_text())
    comment = raw[0]["comments"][0]
    assert comment["body"] == "edited"        # typed field updated
    assert comment["x_reactions"] == 3        # unknown field preserved


def test_merge_only_applies_to_matching_key(tmp_path: Path) -> None:
    """A previous issue with a different key does not bleed into a new one."""
    store = AnvilStore(tmp_path)
    d = tmp_path / "PF"
    d.mkdir(parents=True)
    legacy = serialization.issue_to_dict(_issue("PF-1"))
    legacy["x_future_field"] = "old"
    (d / "issues.json").write_text(json.dumps([legacy]))

    run(store.save_issues("PF", [_issue("PF-2")]))

    raw = json.loads((d / "issues.json").read_text())
    assert "x_future_field" not in raw[0]


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------


def test_empty_store_reports_baseline_version_without_writing(tmp_path: Path) -> None:
    """Absence of a marker maps to the baseline version and touches no disk."""
    store = AnvilStore(tmp_path)
    assert run(store.read_metadata()) == {"schema_version": SCHEMA_VERSION}
    assert run(store.schema_version()) == SCHEMA_VERSION
    assert not (tmp_path / _METADATA_FILENAME).exists()


def test_save_writes_version_marker(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(_project()))
    marker = tmp_path / _METADATA_FILENAME
    assert marker.exists()
    assert json.loads(marker.read_text()) == {"schema_version": SCHEMA_VERSION}
    assert run(store.schema_version()) == SCHEMA_VERSION


def test_marker_is_not_listed_as_a_project(tmp_path: Path) -> None:
    store = AnvilStore(tmp_path)
    run(store.save_project(_project()))
    assert run(store.list_project_keys()) == ["PF"]


def test_legacy_unmarked_store_loads_and_gains_marker_on_save(tmp_path: Path) -> None:
    """A store written before versioning reads as baseline, and its next save
    adds the marker additively without disturbing existing data files."""
    store = AnvilStore(tmp_path)
    d = tmp_path / "PF"
    d.mkdir(parents=True)
    legacy = serialization.issue_to_dict(_issue())
    legacy["x_future_field"] = "keep-me"
    (d / "issues.json").write_text(json.dumps([legacy]))

    # Legacy store: no marker yet, but reads as the baseline version.
    assert not (tmp_path / _METADATA_FILENAME).exists()
    assert run(store.schema_version()) == SCHEMA_VERSION
    assert [i.key for i in run(store.load_issues("PF"))] == ["PF-1"]

    # Next save adds the marker and preserves the pre-existing unknown field.
    run(store.save_issues("PF", [_issue()]))
    assert (tmp_path / _METADATA_FILENAME).exists()
    raw = json.loads((d / "issues.json").read_text())
    assert raw[0]["x_future_field"] == "keep-me"


def test_ensure_metadata_never_overwrites_existing_marker(tmp_path: Path) -> None:
    """A future migration owns version bumps; a save must not silently change
    an already-recorded version."""
    store = AnvilStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / _METADATA_FILENAME
    marker.write_text(json.dumps({"schema_version": 99, "note": "hand-set"}))

    run(store.save_project(_project()))

    assert json.loads(marker.read_text()) == {"schema_version": 99, "note": "hand-set"}
    assert run(store.schema_version()) == 99
