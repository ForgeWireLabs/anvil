"""Tests for the relations / typed_links canonicalization migration.

These pin the decision-0003 contract: ``relations`` is the forward canonical
field, ``typed_links`` is a compatibility mirror, legacy ``typed_links``-only
data upgrades losslessly, no relation is duplicated or silently dropped, and
unknown fields survive. Fixtures under ``tests/fixtures`` stand in for real
legacy and current stores.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import forgewire_anvil as fa
from forgewire_anvil import serialization
from forgewire_anvil.migrations import (merge_relation_records,
                                        migrate_issue_payloads,
                                        migrate_issue_relations)
from forgewire_anvil.store import AnvilStore

FIXTURES = Path(__file__).parent / "fixtures"


def run(coro):
    return asyncio.run(coro)


def _load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Pure canonicalization
# ---------------------------------------------------------------------------


def test_legacy_typed_links_promote_to_relations() -> None:
    [issue] = _load_fixture("legacy_typed_links_only.json")
    assert "relations" not in issue  # legacy payload has none

    migrated = migrate_issue_relations(issue)

    ids = [r["id"] for r in migrated["relations"]]
    assert ids == ["rel-fabric", "rel-job"]
    # typed_links is mirrored, not emptied (compatibility window).
    assert [r["id"] for r in migrated["typed_links"]] == ids


def test_migration_preserves_unknown_top_and_record_fields() -> None:
    [issue] = _load_fixture("legacy_typed_links_only.json")
    migrated = migrate_issue_relations(issue)

    assert migrated["x_legacy_top_field"] == "keep-at-top"
    job_rel = next(r for r in migrated["relations"] if r["id"] == "rel-job")
    assert job_rel["x_record_extra"] == "keep-on-record"
    # Legacy field-name (display_label) is carried through untouched on the
    # payload; the model reader is what maps it to target_label.
    fabric_rel = next(r for r in migrated["relations"] if r["id"] == "rel-fabric")
    assert fabric_rel["display_label"] == "Legacy label name"


def test_migration_does_not_mutate_input() -> None:
    [issue] = _load_fixture("legacy_typed_links_only.json")
    before = json.dumps(issue, sort_keys=True)
    migrate_issue_relations(issue)
    assert json.dumps(issue, sort_keys=True) == before


def test_migration_is_idempotent() -> None:
    [issue] = _load_fixture("legacy_typed_links_only.json")
    once = migrate_issue_relations(issue)
    twice = migrate_issue_relations(once)
    assert once == twice


def test_current_synced_payload_is_stable_under_migration() -> None:
    [issue] = _load_fixture("current_both_synced.json")
    migrated = migrate_issue_relations(issue)
    # Already canonical: one relation, mirrored, no duplication.
    assert [r["id"] for r in migrated["relations"]] == ["rel-1"]
    assert [r["id"] for r in migrated["typed_links"]] == ["rel-1"]


def test_overlapping_relations_and_typed_links_dedup_by_id() -> None:
    issue = {
        "key": "MIX-1",
        "relations": [{"id": "a", "target_type": "job", "target_id": "j1"}],
        "typed_links": [
            {"id": "a", "target_type": "job", "target_id": "j1", "x_extra": 1},
            {"id": "b", "target_type": "job", "target_id": "j2"},
        ],
    }
    migrated = migrate_issue_relations(issue)
    assert [r["id"] for r in migrated["relations"]] == ["a", "b"]
    # Canonical (relations) record wins on known keys, but the typed_links
    # record's unknown key is preserved.
    rel_a = migrated["relations"][0]
    assert rel_a["x_extra"] == 1


def test_duplicate_target_with_different_ids_collapses() -> None:
    """Two records pointing at the same (target_type, target_id) are one
    logical relation and must not both survive."""
    records = [
        {"id": "first", "target_type": "fabric_task", "target_id": "t1"},
        {"id": "second", "target_type": "fabric_task", "target_id": "t1"},
    ]
    merged = merge_relation_records(records)
    assert len(merged) == 1
    assert merged[0]["id"] == "first"  # first occurrence wins


def test_records_without_id_or_target_are_kept_distinct() -> None:
    records = [
        {"note": "no identity 1"},
        {"note": "no identity 2"},
    ]
    merged = merge_relation_records(records)
    assert merged == records


def test_issue_predating_both_relation_fields_is_untouched() -> None:
    """A store written before either field existed has nothing to canonicalize.
    Injecting empty relation lists would rewrite every file and report a
    migration that did not happen."""
    issue = {"id": "i1", "key": "TKT-1", "summary": "Legacy"}
    migrated = migrate_issue_relations(issue)
    assert migrated == issue
    assert "relations" not in migrated
    assert "typed_links" not in migrated


def test_issue_with_empty_relation_lists_is_untouched() -> None:
    issue = {"id": "i1", "key": "TKT-1", "relations": [], "typed_links": []}
    assert migrate_issue_relations(issue) == issue


def test_store_with_no_relations_reports_no_changes(tmp_path: Path) -> None:
    d = tmp_path / "TKT"
    d.mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"key": "TKT", "name": "Legacy"}))
    path = d / "issues.json"
    path.write_text(json.dumps([{"id": "i1", "key": "TKT-1", "summary": "Legacy"}]))
    before = path.read_bytes()

    store = AnvilStore(tmp_path)
    assert run(store.migrate_relations()) == 0
    assert path.read_bytes() == before  # not rewritten


def test_migrate_issue_payloads_counts_only_changed() -> None:
    legacy = _load_fixture("legacy_typed_links_only.json")
    current = _load_fixture("current_both_synced.json")
    _, legacy_changed = migrate_issue_payloads(legacy)
    _, current_changed = migrate_issue_payloads(current)
    assert legacy_changed == 1      # relations added
    assert current_changed == 0     # already canonical


# ---------------------------------------------------------------------------
# Migration survives the serializer round trip (no data loss through models)
# ---------------------------------------------------------------------------


def test_migrated_payload_round_trips_through_serializer() -> None:
    [issue] = _load_fixture("legacy_typed_links_only.json")
    migrated = migrate_issue_relations(issue)

    restored = serialization.issue_from_dict(migrated)
    assert {r.target_id for r in restored.relations} == {"task-aaa", "job-xyz"}
    assert {r.target_id for r in restored.typed_links} == {"task-aaa", "job-xyz"}
    # target_label is recovered from the legacy display_label name.
    fabric = next(r for r in restored.relations if r.target_id == "task-aaa")
    assert fabric.target_label == "Legacy label name"


# ---------------------------------------------------------------------------
# Store-level migration
# ---------------------------------------------------------------------------


def _seed_legacy_store(root: Path) -> Path:
    d = root / "LEG"
    d.mkdir(parents=True)
    # A real store has project.json alongside issues.json; list_project_keys
    # (used by the no-key migration path) only lists dirs that have it.
    (d / "project.json").write_text(json.dumps({"key": "LEG", "name": "Legacy"}))
    path = d / "issues.json"
    path.write_text((FIXTURES / "legacy_typed_links_only.json").read_text())
    return path


def test_store_migrate_relations_upgrades_legacy_store(tmp_path: Path) -> None:
    path = _seed_legacy_store(tmp_path)
    store = AnvilStore(tmp_path)

    changed = run(store.migrate_relations())
    assert changed == 1

    raw = json.loads(path.read_text())
    assert [r["id"] for r in raw[0]["relations"]] == ["rel-fabric", "rel-job"]
    assert raw[0]["x_legacy_top_field"] == "keep-at-top"      # unknown top field
    job = next(r for r in raw[0]["relations"] if r["id"] == "rel-job")
    assert job["x_record_extra"] == "keep-on-record"          # unknown record field


def test_store_migrate_relations_is_idempotent(tmp_path: Path) -> None:
    path = _seed_legacy_store(tmp_path)
    store = AnvilStore(tmp_path)

    assert run(store.migrate_relations()) == 1
    first = path.read_bytes()
    # Second run finds nothing to change and does not rewrite the file.
    assert run(store.migrate_relations()) == 0
    assert path.read_bytes() == first


def test_store_migrate_single_project(tmp_path: Path) -> None:
    _seed_legacy_store(tmp_path)
    store = AnvilStore(tmp_path)
    assert run(store.migrate_relations(project_key="leg")) == 1
