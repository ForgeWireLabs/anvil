"""Tests for the ``anvil`` command-line interface.

These drive main() the way a shell would — argv in, exit code and streams out —
so the contract they pin is the one users actually get: exit 0 on success, 1 on
a planning-domain error (with the stable error code surfaced), 2 on usage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgewire_anvil.cli import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    return tmp_path / "ledger"


def run_cli(ledger: Path, *args: str) -> int:
    return main(["--data-dir", str(ledger), *args])


def run_json(ledger: Path, capsys: pytest.CaptureFixture, *args: str):
    capsys.readouterr()  # drop output from any earlier command in this test
    code = main(["--data-dir", str(ledger), "--json", *args])
    assert code == EXIT_OK
    return json.loads(capsys.readouterr().out)


def _seed(ledger: Path) -> None:
    assert run_cli(ledger, "project", "create", "PF", "Platform") == EXIT_OK
    assert run_cli(ledger, "issue", "create", "PF", "First issue") == EXIT_OK


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def test_no_command_prints_help_and_returns_usage(capsys: pytest.CaptureFixture) -> None:
    assert main([]) == EXIT_USAGE
    assert "ForgeWire Anvil" in capsys.readouterr().out


def test_data_dir_flag_selects_the_ledger(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    payload = run_json(ledger, capsys, "info")
    assert payload["data_dir"] == str(ledger)
    assert payload["schema_version"] == 1


def test_info_lists_projects(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    assert run_json(ledger, capsys, "info")["projects"] == ["PF"]


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


def test_domain_error_reports_stable_code_on_stderr(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    # Looking up an issue in a project that does not exist surfaces as a
    # missing issue, which is what the caller asked about.
    assert run_cli(ledger, "issue", "get", "NOPE-1") == EXIT_ERROR
    assert "ISSUE_NOT_FOUND" in capsys.readouterr().err


def test_missing_project_reports_its_own_code(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    assert run_cli(ledger, "project", "get", "GHOST") == EXIT_ERROR
    assert "PROJECT_NOT_FOUND" in capsys.readouterr().err


def test_invalid_transition_reports_its_code(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed(ledger)
    assert run_cli(ledger, "transition", "PF-1", "done") == EXIT_ERROR
    assert "INVALID_TRANSITION" in capsys.readouterr().err


def test_validation_error_reports_its_code(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    assert run_cli(ledger, "project", "create", "", "Nameless") == EXIT_ERROR
    assert "VALIDATION_ERROR" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Projects and issues
# ---------------------------------------------------------------------------


def test_project_lifecycle(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    assert run_cli(ledger, "project", "create", "PF", "Platform") == EXIT_OK
    assert [p["key"] for p in run_json(ledger, capsys, "project", "list")] == ["PF"]
    assert run_json(ledger, capsys, "project", "get", "pf")["name"] == "Platform"
    assert run_cli(ledger, "project", "delete", "PF") == EXIT_OK
    assert run_json(ledger, capsys, "project", "list") == []


def test_issue_create_and_get(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    run_cli(ledger, "project", "create", "PF", "Platform")
    payload = run_json(
        ledger, capsys, "issue", "create", "PF", "Fix widget",
        "--priority", "high", "--label", "urgent", "--label", "backend",
        "--field", "team=core",
    )
    assert payload["key"] == "PF-1"
    assert payload["priority"] == "high"
    assert payload["labels"] == ["urgent", "backend"]
    assert payload["custom_fields"] == {"team": "core"}


def test_issue_update_and_delete(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    payload = run_json(ledger, capsys, "issue", "update", "PF-1", "--summary", "Changed")
    assert payload["summary"] == "Changed"
    assert run_cli(ledger, "issue", "delete", "PF-1") == EXIT_OK
    assert run_cli(ledger, "issue", "get", "PF-1") == EXIT_ERROR


def test_assignee_parsing_accepts_id_and_display_name(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    run_cli(ledger, "project", "create", "PF", "Platform")
    payload = run_json(
        ledger, capsys, "issue", "create", "PF", "Assigned", "--assignee", "u1:Alice",
    )
    assert payload["assignee"] == {"id": "u1", "display_name": "Alice", "email": None}


def test_bad_key_value_field_is_rejected(ledger: Path) -> None:
    run_cli(ledger, "project", "create", "PF", "Platform")
    with pytest.raises(SystemExit):
        run_cli(ledger, "issue", "create", "PF", "Bad", "--field", "novalue")


# ---------------------------------------------------------------------------
# Search, transitions, comments
# ---------------------------------------------------------------------------


def test_search_filters_and_paginates(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    run_cli(ledger, "project", "create", "PF", "Platform")
    for n in range(3):
        run_cli(ledger, "issue", "create", "PF", f"Issue {n}", "--label", "x")

    assert run_json(ledger, capsys, "search", "--project", "PF")["total"] == 3
    assert run_json(ledger, capsys, "search", "--text", "Issue 1")["total"] == 1
    assert run_json(ledger, capsys, "search", "--label", "x")["total"] == 3

    page = run_json(ledger, capsys, "search", "--limit", "2")
    assert len(page["issues"]) == 2
    assert page["total"] == 3


def test_transitions_then_transition(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    targets = {t["to_status"] for t in run_json(ledger, capsys, "transitions", "PF-1")}
    assert "todo" in targets
    assert run_json(ledger, capsys, "transition", "PF-1", "todo")["status"] == "todo"


def test_comment_add(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    assert run_json(
        ledger, capsys, "comment", "add", "PF-1", "Looks good", "--author", "u1:Alice",
    )["body"] == "Looks good"


# ---------------------------------------------------------------------------
# Boards and sprints
# ---------------------------------------------------------------------------


def test_board_list_and_get(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    boards = run_json(ledger, capsys, "board", "list", "--project", "PF")
    assert len(boards) == 1
    assert run_json(ledger, capsys, "board", "get", boards[0]["id"])["name"] == "Platform Board"


def test_sprint_lifecycle(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    board_id = run_json(ledger, capsys, "board", "list", "--project", "PF")[0]["id"]

    sprint = run_json(ledger, capsys, "sprint", "create", board_id, "Sprint 1", "--goal", "Ship")
    assert sprint["state"] == "future"
    assert run_json(ledger, capsys, "sprint", "start", sprint["id"])["state"] == "active"
    assert run_json(ledger, capsys, "sprint", "close", sprint["id"])["state"] == "closed"


# ---------------------------------------------------------------------------
# Links and relations
# ---------------------------------------------------------------------------


def test_link_add_and_remove(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    run_cli(ledger, "issue", "create", "PF", "Second")
    link = run_json(ledger, capsys, "link", "add", "PF-1", "PF-2", "--type", "blocks")
    assert link["target_key"] == "PF-2"
    assert run_cli(ledger, "link", "remove", "PF-1", link["id"]) == EXIT_OK
    assert run_json(ledger, capsys, "issue", "get", "PF-1")["links"] == []


def test_relation_add_list_remove(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    relation = run_json(
        ledger, capsys, "relation", "add", "PF-1", "fabric_task", "task-1",
        "--label", "Build", "--meta", "terminal_status=running",
    )
    assert relation["target_id"] == "task-1"

    listed = run_json(ledger, capsys, "relation", "list", "PF-1")
    assert [r["id"] for r in listed] == [relation["id"]]

    assert run_cli(ledger, "relation", "remove", "PF-1", relation["id"]) == EXIT_OK
    assert run_json(ledger, capsys, "relation", "list", "PF-1") == []


# ---------------------------------------------------------------------------
# Export / import / validate / migrate
# ---------------------------------------------------------------------------


def test_export_to_stdout(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    capsys.readouterr()  # drop the seeding output
    assert run_cli(ledger, "export") == EXIT_OK
    bundle = json.loads(capsys.readouterr().out)
    assert bundle["anvil_export_version"] == 1
    assert bundle["projects"][0]["project"]["key"] == "PF"


def test_export_import_round_trip_via_files(
    ledger: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed(ledger)
    bundle_path = tmp_path / "backup.json"
    assert run_cli(ledger, "export", "-o", str(bundle_path)) == EXIT_OK
    assert bundle_path.exists()

    restored = tmp_path / "restored"
    assert run_cli(restored, "import", str(bundle_path)) == EXIT_OK
    assert run_json(restored, capsys, "issue", "get", "PF-1")["summary"] == "First issue"


def test_import_refuses_to_clobber_without_overwrite(
    ledger: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed(ledger)
    bundle_path = tmp_path / "backup.json"
    run_cli(ledger, "export", "-o", str(bundle_path))

    assert run_cli(ledger, "import", str(bundle_path)) == EXIT_ERROR
    assert "VALIDATION_ERROR" in capsys.readouterr().err
    assert run_cli(ledger, "import", str(bundle_path), "--overwrite") == EXIT_OK


def test_import_missing_file_is_an_error(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    assert run_cli(ledger, "import", str(ledger / "nope.json")) == EXIT_ERROR
    assert "error" in capsys.readouterr().err


def test_validate_ok_and_failing(ledger: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(ledger)
    assert run_cli(ledger, "validate") == EXIT_OK
    assert "ok: no problems found" in capsys.readouterr().out

    (ledger / "PF" / "issues.json").write_text("{ not json")
    assert run_cli(ledger, "validate") == EXIT_ERROR
    assert "problems:" in capsys.readouterr().out


def test_migrate_canonicalizes_legacy_relations(
    ledger: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed(ledger)
    path = ledger / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0].pop("relations", None)
    raw[0]["typed_links"] = [
        {"id": "rel-1", "source_key": "PF-1", "target_type": "job", "target_id": "j1"}
    ]
    path.write_text(json.dumps(raw))

    assert run_json(ledger, capsys, "migrate", "relations")["changed"] == 1
    assert [r["id"] for r in run_json(ledger, capsys, "relation", "list", "PF-1")] == ["rel-1"]


def test_migrate_store_adopts_a_legacy_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The upgrade path off the old working-directory-relative ledger."""
    legacy = tmp_path / "data" / "issue_tracker"
    _seed(legacy)

    new_ledger = tmp_path / "user-ledger"
    payload = run_json(new_ledger, capsys, "migrate", "store", str(legacy))
    assert payload["migrated"] == 1

    assert run_json(new_ledger, capsys, "issue", "get", "PF-1")["summary"] == "First issue"
    # The source ledger is read-only during migration; it must still be intact.
    assert run_json(legacy, capsys, "issue", "get", "PF-1")["summary"] == "First issue"
