"""Anvil JSON-file persistence for the planning ledger.

Stores each project as a directory under a configurable root, with
``project.json``, ``issues.json``, and ``boards.json`` files.  All
writes are atomic (write-to-temp then rename) and thread-safe via
``asyncio.Lock``.

This is the developer-preview store: human-inspectable, atomically
written, and single-process. It implements the
:class:`~forgewire_anvil.protocols.IssueStore` contract and preserves
unknown and legacy record fields on round trip so that data written by
older or newer Anvil builds survives being loaded and re-saved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .migrations import migrate_issue_payloads
from .paths import resolve_data_dir
from .serialization import (board_from_dict, board_to_dict, issue_from_dict,
                            issue_to_dict, project_from_dict, project_to_dict)
from .models import Board, Issue, Project

logger = logging.getLogger(__name__)

#: On-disk format version for stores written by this package. Existing stores
#: predate the version marker; their format is identical to version 1, so a
#: store with no marker file is treated as this baseline version rather than as
#: an unknown/corrupt store.
SCHEMA_VERSION = 1

#: Sidecar file, at the store root, that records the store's schema version and
#: metadata. It is intentionally *not* a project directory (dotfile) so it never
#: appears in :meth:`AnvilStore.list_project_keys`. The per-project data files
#: (``project.json``, ``issues.json``, ``boards.json``) are left untouched by
#: versioning so their on-disk bytes remain stable across releases.
_METADATA_FILENAME = ".anvil-store.json"


class AnvilStore:
    """Anvil JSON-file backed storage for planning data.

    Directory layout::

        <root>/
          .anvil-store.json  – schema version marker
          <PROJECT_KEY>/
            project.json   – project metadata + next-issue counter
            issues.json    – list of all issues
            boards.json    – list of boards (with embedded sprints)

    *root* defaults to the user-scoped data directory (see
    :func:`forgewire_anvil.paths.resolve_data_dir`, which honors
    ``ANVIL_DATA_DIR``). Pass *root* explicitly to point at a specific store.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        # Resolved per instance, not at import, so ANVIL_DATA_DIR set by a
        # launcher (or a test) after import is still honored. Omitting *root*
        # selects the user-scoped directory, never a path relative to the
        # process's working directory.
        self._root = resolve_data_dir(root)
        self._lock = asyncio.Lock()

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Schema metadata
    # ------------------------------------------------------------------

    def _metadata_path(self) -> Path:
        return self._root / _METADATA_FILENAME

    async def read_metadata(self) -> dict[str, Any]:
        """Return the store's schema metadata.

        A store written before schema versioning has no marker file; its format
        is the baseline, so absence maps to ``{"schema_version": SCHEMA_VERSION}``
        rather than an error. This never writes to disk.
        """
        data = self._read_json(self._metadata_path())
        if not isinstance(data, dict):
            return {"schema_version": SCHEMA_VERSION}
        return data

    async def schema_version(self) -> int:
        """Return the store's recorded schema version (baseline if unmarked)."""
        meta = await self.read_metadata()
        version = meta.get("schema_version", SCHEMA_VERSION)
        return version if isinstance(version, int) else SCHEMA_VERSION

    def _ensure_metadata(self) -> None:
        """Write the version marker if absent — additively, never overwriting.

        Called from write paths so new stores are versioned and legacy stores
        gain a marker on their next save without touching any existing data
        file. An existing marker is left as-is so a future migration owns any
        version bump; ``_ensure_metadata`` never silently changes a version.
        """
        path = self._metadata_path()
        if path.exists():
            return
        self._atomic_write(path, {"schema_version": SCHEMA_VERSION})

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def _project_dir(self, key: str) -> Path:
        return self._root / key.upper()

    def _ensure_dir(self, key: str) -> Path:
        d = self._project_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _atomic_write(self, path: Path, data: Any) -> None:
        """Write JSON atomically (temp file + rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, str(path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read_json(self, path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default
        with open(path) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Project persistence
    # ------------------------------------------------------------------

    async def save_project(self, project: Project) -> None:
        async with self._lock:
            d = self._ensure_dir(project.key)
            self._ensure_metadata()
            self._atomic_write(d / "project.json", project_to_dict(project))

    async def load_project(self, key: str) -> Project | None:
        path = self._project_dir(key) / "project.json"
        data = self._read_json(path)
        if data is None:
            return None
        return project_from_dict(data)

    async def delete_project(self, key: str) -> None:
        import shutil
        async with self._lock:
            d = self._project_dir(key)
            if d.exists():
                shutil.rmtree(d)

    async def list_project_keys(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            d.name
            for d in self._root.iterdir()
            if d.is_dir() and (d / "project.json").exists()
        )

    # ------------------------------------------------------------------
    # Issue persistence
    # ------------------------------------------------------------------

    async def save_issues(self, project_key: str, issues: list[Issue]) -> None:
        async with self._lock:
            d = self._ensure_dir(project_key)
            self._ensure_metadata()
            path = d / "issues.json"
            existing = self._read_json(path, default=[])
            existing_by_key = {
                item.get("key"): item
                for item in existing
                if isinstance(item, dict) and item.get("key")
            }

            payload: list[dict[str, Any]] = []
            for issue in issues:
                serialized = issue_to_dict(issue)
                previous = existing_by_key.get(issue.key)
                if previous:
                    # Preserve unknown top-level and nested record fields from
                    # legacy or future Anvil JSON while allowing typed model
                    # fields to be updated by the current serializer.
                    serialized = self._merge_issue_payload(previous, serialized)
                payload.append(serialized)

            self._atomic_write(path, payload)

    @staticmethod
    def _merge_issue_payload(
        previous: dict[str, Any],
        serialized: dict[str, Any],
    ) -> dict[str, Any]:
        merged = {**previous, **serialized}
        for field_name in (
            "comments",
            "links",
            "relations",
            "typed_links",
            "activity_log",
        ):
            merged[field_name] = AnvilStore._merge_record_list(
                previous.get(field_name, []),
                serialized.get(field_name, []),
            )
        return merged

    @staticmethod
    def _merge_record_list(
        previous: Any,
        serialized: Any,
    ) -> Any:
        if not isinstance(previous, list) or not isinstance(serialized, list):
            return serialized

        previous_by_id = {
            item.get("id"): item
            for item in previous
            if isinstance(item, dict) and item.get("id")
        }
        return [
            {**previous_by_id[item.get("id")], **item}
            if isinstance(item, dict) and item.get("id") in previous_by_id
            else item
            for item in serialized
        ]

    async def load_issues(self, project_key: str) -> list[Issue]:
        path = self._project_dir(project_key) / "issues.json"
        data = self._read_json(path, default=[])
        return [issue_from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Board persistence
    # ------------------------------------------------------------------

    async def save_boards(self, project_key: str, boards: list[Board]) -> None:
        async with self._lock:
            d = self._ensure_dir(project_key)
            self._ensure_metadata()
            self._atomic_write(
                d / "boards.json",
                [board_to_dict(b) for b in boards],
            )

    async def load_boards(self, project_key: str) -> list[Board]:
        path = self._project_dir(project_key) / "boards.json"
        data = self._read_json(path, default=[])
        return [board_from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Payload-level access
    #
    # The model readers keep only known fields, so a load/save round trip
    # through Issue/Board/Project silently drops anything this build does not
    # understand. Import, export, and backup must not do that (decision 0003:
    # no release may silently discard unknown JSON fields). These read and
    # write the stored records verbatim, with no model round trip.
    # ------------------------------------------------------------------

    async def load_project_payload(self, key: str) -> dict[str, Any] | None:
        data = self._read_json(self._project_dir(key) / "project.json")
        return data if isinstance(data, dict) else None

    async def load_issue_payloads(self, project_key: str) -> list[Any]:
        data = self._read_json(self._project_dir(project_key) / "issues.json", default=[])
        return data if isinstance(data, list) else []

    async def load_board_payloads(self, project_key: str) -> list[Any]:
        data = self._read_json(self._project_dir(project_key) / "boards.json", default=[])
        return data if isinstance(data, list) else []

    async def save_project_payload(self, key: str, payload: dict[str, Any]) -> None:
        """Write a project payload verbatim, replacing any existing record."""
        async with self._lock:
            d = self._ensure_dir(key)
            self._ensure_metadata()
            self._atomic_write(d / "project.json", payload)

    async def save_issue_payloads(self, project_key: str, payloads: list[Any]) -> None:
        """Write issue payloads verbatim, replacing the existing file.

        Unlike :meth:`save_issues` this does not merge with what is already
        stored: a restore is authoritative, so the incoming payloads are the
        record rather than an update to be merged into one.
        """
        async with self._lock:
            d = self._ensure_dir(project_key)
            self._ensure_metadata()
            self._atomic_write(d / "issues.json", payloads)

    async def save_board_payloads(self, project_key: str, payloads: list[Any]) -> None:
        """Write board payloads verbatim, replacing the existing file."""
        async with self._lock:
            d = self._ensure_dir(project_key)
            self._ensure_metadata()
            self._atomic_write(d / "boards.json", payloads)

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def migrate_relations(self, project_key: str | None = None) -> int:
        """Canonicalize typed relations across stored issues.

        Rewrites each project's ``issues.json`` so ``relations`` is the
        deduplicated canonical set and ``typed_links`` mirrors it (see
        :func:`forgewire_anvil.migrations.migrate_issue_relations`). The rewrite
        is payload-level, so unknown and legacy fields are preserved. A project
        whose issues are already canonical is left untouched (no rewrite, so its
        on-disk bytes are stable). Returns the number of issues changed.

        Pass *project_key* to migrate a single project; omit it for every
        project in the store.
        """
        if project_key is None:
            keys = await self.list_project_keys()
        else:
            keys = [project_key.upper()]

        total_changed = 0
        async with self._lock:
            for key in keys:
                path = self._project_dir(key) / "issues.json"
                data = self._read_json(path, default=None)
                if not isinstance(data, list):
                    continue
                migrated, changed = migrate_issue_payloads(data)
                if changed:
                    self._ensure_metadata()
                    self._atomic_write(path, migrated)
                    total_changed += changed
        return total_changed
