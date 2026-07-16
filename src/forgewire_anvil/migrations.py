"""Schema migrations for ForgeWire Anvil stored data.

These operate on raw issue *payloads* (the plain dicts stored in
``issues.json``) rather than on :class:`~forgewire_anvil.models.Issue`
instances, so unknown and legacy fields survive: the model readers keep only
known fields, whereas a payload-level migration can preserve everything on
disk while reconciling the parts it understands.

Relation-field canonicalization
--------------------------------

Per decision 0003, ``Issue.relations`` is the forward canonical field for
provider-neutral links to non-issue work objects. ``Issue.typed_links`` is an
earlier name for the same records and is retained as a **compatibility read
window**: existing ``typed_links`` data must remain readable, and no relation
may be silently dropped. :func:`migrate_issue_relations` reconciles the two
lists onto ``relations`` (deduplicated) while mirroring the result back into
``typed_links`` so downlevel readers keep working. It is pure and idempotent.
"""

from __future__ import annotations

from typing import Any

#: Fields whose values identify the *same logical relation* even across the two
#: list names. Records that share a non-empty id, or a non-empty
#: ``(target_type, target_id)`` pair, are collapsed into one — matching the
#: provider's own dedup key so a migrated store looks like a provider-written
#: one.
_RELATION_LIST_FIELDS = ("relations", "typed_links")


def _as_record_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _target_key(record: dict[str, Any]) -> tuple[Any, Any] | None:
    target_id = record.get("target_id")
    if not target_id:
        return None
    return (record.get("target_type"), target_id)


def merge_relation_records(records: list[Any]) -> list[Any]:
    """Deduplicate an ordered sequence of relation payloads.

    Order is preserved by first appearance. Two records collapse when they
    share a non-empty ``id`` or a non-empty ``(target_type, target_id)`` pair.
    On collapse, the earlier (higher-precedence) record's known values win,
    while unknown keys contributed by the later record are preserved — nothing
    a record carried is discarded. Non-dict entries pass through untouched.
    """
    merged: list[Any] = []
    index_by_id: dict[Any, int] = {}
    index_by_target: dict[tuple[Any, Any], int] = {}

    def _register(idx: int, record: dict[str, Any]) -> None:
        rid = record.get("id")
        if rid:
            index_by_id[rid] = idx
        tkey = _target_key(record)
        if tkey is not None:
            index_by_target[tkey] = idx

    for record in records:
        if not isinstance(record, dict):
            merged.append(record)
            continue

        rid = record.get("id")
        tkey = _target_key(record)

        existing_index: int | None = None
        if rid and rid in index_by_id:
            existing_index = index_by_id[rid]
        elif tkey is not None and tkey in index_by_target:
            existing_index = index_by_target[tkey]

        if existing_index is None:
            merged.append(dict(record))
            _register(len(merged) - 1, merged[-1])
        else:
            existing = merged[existing_index]
            if isinstance(existing, dict):
                # Earlier record wins on known keys; later record's unknown
                # keys are preserved. No field is dropped.
                merged[existing_index] = {**record, **existing}
                _register(existing_index, merged[existing_index])

    return merged


def migrate_issue_relations(issue: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize one issue payload's typed relations onto ``relations``.

    Returns a new top-level dict (the input is not mutated). ``relations``
    becomes the deduplicated union of the incoming ``relations`` followed by
    ``typed_links`` (canonical precedence to ``relations``). ``typed_links`` is
    rewritten to mirror that canonical set, so it stays a faithful
    compatibility window rather than drifting or being emptied. All other keys,
    including unknown ones, are preserved. The function is idempotent:
    ``migrate_issue_relations(migrate_issue_relations(x)) == migrate_issue_relations(x)``.
    """
    result = dict(issue)
    combined = _as_record_list(issue.get("relations")) + _as_record_list(
        issue.get("typed_links")
    )
    if not combined:
        # Nothing to canonicalize. Return the payload untouched rather than
        # injecting empty relation lists: an issue that predates both fields is
        # already canonical, and adding empty keys would rewrite every file in a
        # legacy store and report a migration that did not happen.
        return result

    canonical = merge_relation_records(combined)
    result["relations"] = canonical
    result["typed_links"] = [
        dict(record) if isinstance(record, dict) else record for record in canonical
    ]
    return result


def migrate_issue_payloads(issues: list[Any]) -> tuple[list[Any], int]:
    """Apply :func:`migrate_issue_relations` to a list of issue payloads.

    Returns the migrated list and the count of payloads whose relation fields
    actually changed, so a caller can skip rewriting an already-canonical store.
    """
    migrated: list[Any] = []
    changed = 0
    for issue in issues:
        if not isinstance(issue, dict):
            migrated.append(issue)
            continue
        new_issue = migrate_issue_relations(issue)
        if any(new_issue.get(f) != issue.get(f) for f in _RELATION_LIST_FIELDS):
            changed += 1
        migrated.append(new_issue)
    return migrated, changed
