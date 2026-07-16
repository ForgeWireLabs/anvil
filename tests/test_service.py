"""Tests for the standalone Anvil service facade.

These pin the facade's error contract (it raises the typed hierarchy rather
than wrapping results), the export/import bundle round trip including unknown
fields, and the validation report.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import forgewire_anvil as fa
from forgewire_anvil.service import EXPORT_VERSION, Anvil, validate_bundle


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def anvil(tmp_path: Path) -> Anvil:
    return Anvil(tmp_path / "ledger")


def _seed(anvil: Anvil, key: str = "PF") -> None:
    run(anvil.provider.create_project(key=key, name="Platform"))
    run(anvil.provider.create_issue(project_key=key, summary="First issue"))


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_data_dir_is_explicit_when_given(tmp_path: Path) -> None:
    anvil = Anvil(tmp_path / "ledger")
    assert anvil.data_dir == tmp_path / "ledger"


def test_data_dir_honors_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fa.DATA_DIR_ENV_VAR, str(tmp_path / "from-env"))
    assert Anvil().data_dir == tmp_path / "from-env"


def test_exposes_provider_and_store(anvil: Anvil) -> None:
    assert isinstance(anvil.provider, fa.AnvilProvider)
    assert isinstance(anvil.store, fa.AnvilStore)
    assert isinstance(anvil.provider, fa.IssueTrackerProvider)


def test_schema_version(anvil: Anvil) -> None:
    assert run(anvil.schema_version()) == fa.SCHEMA_VERSION


def test_close_is_safe(anvil: Anvil) -> None:
    run(anvil.close())


# ---------------------------------------------------------------------------
# Error contract — the facade raises, it does not wrap
# ---------------------------------------------------------------------------


def test_facade_raises_typed_errors_with_stable_codes(anvil: Anvil) -> None:
    with pytest.raises(fa.ProjectNotFoundError) as excinfo:
        run(anvil.export_store(project_key="NOPE"))
    assert excinfo.value.error_code == "PROJECT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------


def test_export_empty_store(anvil: Anvil) -> None:
    bundle = run(anvil.export_store())
    assert bundle["anvil_export_version"] == EXPORT_VERSION
    assert bundle["schema_version"] == fa.SCHEMA_VERSION
    assert bundle["projects"] == []


def test_export_includes_projects_issues_and_boards(anvil: Anvil) -> None:
    _seed(anvil)
    bundle = run(anvil.export_store())
    [entry] = bundle["projects"]
    assert entry["project"]["key"] == "PF"
    assert [i["key"] for i in entry["issues"]] == ["PF-1"]
    assert len(entry["boards"]) == 1  # default board


def test_export_single_project(anvil: Anvil) -> None:
    _seed(anvil, "PF")
    _seed(anvil, "AX")
    bundle = run(anvil.export_store(project_key="pf"))
    assert [e["project"]["key"] for e in bundle["projects"]] == ["PF"]


def test_export_unknown_project_raises(anvil: Anvil) -> None:
    with pytest.raises(fa.ProjectNotFoundError):
        run(anvil.export_store(project_key="GHOST"))


def test_export_import_round_trip_into_a_fresh_ledger(anvil: Anvil, tmp_path: Path) -> None:
    _seed(anvil)
    bundle = run(anvil.export_store())

    restored = Anvil(tmp_path / "restored")
    assert run(restored.import_store(bundle)) == 1

    issue = run(restored.provider.get_issue("PF-1"))
    assert issue.summary == "First issue"
    assert [b.project_key for b in run(restored.provider.list_boards(project_key="PF"))] == ["PF"]


def test_import_preserves_unknown_fields(anvil: Anvil, tmp_path: Path) -> None:
    """A bundle carrying fields this build doesn't know must not lose them."""
    _seed(anvil)
    bundle = run(anvil.export_store())
    bundle["projects"][0]["issues"][0]["x_future_field"] = "keep-me"

    restored = Anvil(tmp_path / "restored")
    run(restored.import_store(bundle))

    raw = json.loads((restored.data_dir / "PF" / "issues.json").read_text())
    assert raw[0]["x_future_field"] == "keep-me"


def test_export_preserves_unknown_fields_already_on_disk(anvil: Anvil) -> None:
    """Export must read at the payload level: a model round trip would drop
    fields this build does not know, silently corrupting a backup."""
    _seed(anvil)
    path = anvil.data_dir / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0]["x_future_field"] = "keep-me"
    raw[0]["comments"] = [{"id": "c1", "body": "hi", "x_reactions": 3}]
    path.write_text(json.dumps(raw))

    bundle = run(anvil.export_store())
    exported = bundle["projects"][0]["issues"][0]
    assert exported["x_future_field"] == "keep-me"
    assert exported["comments"][0]["x_reactions"] == 3


def test_backup_restore_round_trip_is_byte_faithful(anvil: Anvil, tmp_path: Path) -> None:
    """The backup/restore path an operator actually relies on: export a store
    carrying unknown fields, restore it elsewhere, and get the same records."""
    _seed(anvil)
    path = anvil.data_dir / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0]["x_future_field"] = "keep-me"
    path.write_text(json.dumps(raw))

    bundle = run(anvil.export_store())
    restored = Anvil(tmp_path / "restored")
    run(restored.import_store(bundle))

    original = json.loads((anvil.data_dir / "PF" / "issues.json").read_text())
    copied = json.loads((restored.data_dir / "PF" / "issues.json").read_text())
    assert copied == original


def test_import_refuses_to_clobber_by_default(anvil: Anvil) -> None:
    _seed(anvil)
    bundle = run(anvil.export_store())
    with pytest.raises(fa.ValidationError):
        run(anvil.import_store(bundle))


def test_import_overwrite_replaces(anvil: Anvil) -> None:
    _seed(anvil)
    bundle = run(anvil.export_store())
    assert run(anvil.import_store(bundle, overwrite=True)) == 1


# ---------------------------------------------------------------------------
# Bundle validation
# ---------------------------------------------------------------------------


def test_validate_bundle_accepts_a_real_export(anvil: Anvil) -> None:
    _seed(anvil)
    validate_bundle(run(anvil.export_store()))


@pytest.mark.parametrize("bad", ["not-a-dict", 42, None, []])
def test_validate_bundle_rejects_non_objects(bad: object) -> None:
    with pytest.raises(fa.ValidationError):
        validate_bundle(bad)


def test_validate_bundle_rejects_wrong_export_version() -> None:
    with pytest.raises(fa.ValidationError):
        validate_bundle({"anvil_export_version": 999, "projects": []})


def test_validate_bundle_rejects_newer_schema_version() -> None:
    with pytest.raises(fa.ValidationError):
        validate_bundle({
            "anvil_export_version": EXPORT_VERSION,
            "schema_version": fa.SCHEMA_VERSION + 1,
            "projects": [],
        })


def test_validate_bundle_rejects_bad_projects_shape() -> None:
    with pytest.raises(fa.ValidationError):
        validate_bundle({"anvil_export_version": EXPORT_VERSION, "projects": "nope"})


def test_validate_bundle_rejects_keyless_project() -> None:
    with pytest.raises(fa.ValidationError):
        validate_bundle({
            "anvil_export_version": EXPORT_VERSION,
            "projects": [{"project": {"name": "no key"}}],
        })


# ---------------------------------------------------------------------------
# Store validation report
# ---------------------------------------------------------------------------


def test_validate_reports_ok_for_a_healthy_store(anvil: Anvil) -> None:
    _seed(anvil)
    report = run(anvil.validate())
    assert report["ok"] is True
    assert report["problems"] == []
    assert report["projects"] == ["PF"]
    assert report["schema_version"] == fa.SCHEMA_VERSION


def test_validate_reports_all_problems_not_just_the_first(anvil: Anvil) -> None:
    _seed(anvil)
    # Corrupt the issues file so it cannot be read back.
    (anvil.data_dir / "PF" / "issues.json").write_text("{ not json")
    report = run(anvil.validate())
    assert report["ok"] is False
    assert any("PF" in p for p in report["problems"])


def test_validate_flags_issue_claiming_the_wrong_project(anvil: Anvil) -> None:
    _seed(anvil)
    path = anvil.data_dir / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0]["project_key"] = "OTHER"
    path.write_text(json.dumps(raw))

    report = run(anvil.validate())
    assert report["ok"] is False
    assert any("claims project" in p for p in report["problems"])


# ---------------------------------------------------------------------------
# Migration passthrough
# ---------------------------------------------------------------------------


def test_migrate_from_adopts_a_legacy_store(anvil: Anvil, tmp_path: Path) -> None:
    """Adopting the legacy data/issue_tracker layout is lossless and
    non-destructive to the source."""
    legacy = Anvil(tmp_path / "data" / "issue_tracker")
    _seed(legacy)
    path = legacy.data_dir / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0]["x_future_field"] = "keep-me"
    path.write_text(json.dumps(raw))

    assert run(anvil.migrate_from(legacy.data_dir)) == 1

    migrated = json.loads((anvil.data_dir / "PF" / "issues.json").read_text())
    assert migrated[0]["x_future_field"] == "keep-me"
    # The source is only read; it survives untouched.
    assert json.loads(path.read_text()) == migrated


def test_migrate_from_refuses_to_clobber_by_default(anvil: Anvil, tmp_path: Path) -> None:
    legacy = Anvil(tmp_path / "legacy")
    _seed(legacy)
    _seed(anvil)
    with pytest.raises(fa.ValidationError):
        run(anvil.migrate_from(legacy.data_dir))
    assert run(anvil.migrate_from(legacy.data_dir, overwrite=True)) == 1


def test_migrate_delegates_to_the_store(anvil: Anvil) -> None:
    _seed(anvil)
    path = anvil.data_dir / "PF" / "issues.json"
    raw = json.loads(path.read_text())
    raw[0].pop("relations", None)
    raw[0]["typed_links"] = [
        {"id": "rel-1", "source_key": "PF-1", "target_type": "job", "target_id": "j1"}
    ]
    path.write_text(json.dumps(raw))

    assert run(anvil.migrate()) == 1
    issue = run(anvil.provider.get_issue("PF-1"))
    assert [r.id for r in issue.relations] == ["rel-1"]
