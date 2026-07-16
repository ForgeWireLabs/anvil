"""The standalone ForgeWire Anvil service facade.

:class:`Anvil` is the front door for embedding the planning ledger: it wires a
data directory to a store and a provider, and adds the whole-store operations
that sit above a single provider — export, import, validation, and migration.

Error contract
--------------

The facade raises; it does not wrap. Every failure is an
:class:`~forgewire_anvil.exceptions.IssueTrackerError` subclass carrying a
stable error code (``IssueNotFoundError``, ``ValidationError``,
``ProjectExistsError``, ...). There is deliberately no result/either type here:
the exception hierarchy *is* the explicit contract, so embedding applications
map it once at their own boundary rather than unwrapping a second envelope.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import ProjectNotFoundError, ValidationError
from .paths import resolve_data_dir
from .provider import AnvilProvider
from .store import SCHEMA_VERSION, AnvilStore

#: Version of the export envelope produced by :meth:`Anvil.export_store`. This
#: is the *bundle* format and is versioned independently of the on-disk store
#: schema, which travels inside the bundle as ``schema_version``.
EXPORT_VERSION = 1


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Anvil:
    """A configured Anvil planning ledger.

    Parameters
    ----------
    data_dir:
        Where the ledger lives. Omit to use the user-scoped directory
        (honoring ``ANVIL_DATA_DIR``); see
        :func:`forgewire_anvil.paths.resolve_data_dir`.
    """

    def __init__(self, data_dir: str | os.PathLike[str] | None = None) -> None:
        self._root = resolve_data_dir(data_dir)
        self._store = AnvilStore(self._root)
        self._provider = AnvilProvider(self._store)

    # -- Wiring ---------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        """The resolved directory this ledger reads and writes."""
        return self._root

    @property
    def provider(self) -> AnvilProvider:
        """The underlying provider, for the full issue-tracker surface."""
        return self._provider

    @property
    def store(self) -> AnvilStore:
        """The underlying store, for storage-level operations."""
        return self._store

    async def close(self) -> None:
        await self._provider.close()

    async def schema_version(self) -> int:
        """The store's recorded schema version (baseline if unmarked)."""
        return await self._store.schema_version()

    # -- Migration ------------------------------------------------------

    async def migrate(self, project_key: str | None = None) -> int:
        """Canonicalize typed relations across the store.

        Returns the number of issues changed. See
        :meth:`forgewire_anvil.store.AnvilStore.migrate_relations`.
        """
        return await self._store.migrate_relations(project_key)

    async def migrate_from(
        self,
        source_dir: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> int:
        """Adopt an existing ledger from *source_dir* into this one.

        This is the upgrade path off the legacy working-directory-relative
        layout (``data/issue_tracker``), which is no longer a default location:
        point at the old directory and its projects are copied into this
        ledger. Records move at the payload level, so unknown and legacy fields
        survive. The source is only read — it is never modified or removed, so
        a failed migration leaves the original intact.

        Returns the number of projects migrated.
        """
        source = Anvil(source_dir)
        try:
            bundle = await source.export_store()
        finally:
            await source.close()
        return await self.import_store(bundle, overwrite=overwrite)

    # -- Export / import ------------------------------------------------

    async def export_store(self, project_key: str | None = None) -> dict[str, Any]:
        """Export the ledger (or one project) as a self-describing bundle.

        The bundle carries the stored records verbatim — read at the payload
        level, never through the models — so unknown and legacy fields survive
        an export/import round trip instead of being quietly dropped by a
        build that does not know about them.
        """
        if project_key is None:
            keys = await self._store.list_project_keys()
        else:
            key = project_key.upper()
            if await self._store.load_project_payload(key) is None:
                raise ProjectNotFoundError(project_key)
            keys = [key]

        projects: list[dict[str, Any]] = []
        for key in keys:
            project = await self._store.load_project_payload(key)
            if project is None:
                continue
            projects.append({
                "project": project,
                "issues": await self._store.load_issue_payloads(key),
                "boards": await self._store.load_board_payloads(key),
            })

        return {
            "anvil_export_version": EXPORT_VERSION,
            "schema_version": await self._store.schema_version(),
            "exported_at": _utcnow_iso(),
            "projects": projects,
        }

    async def import_store(
        self,
        bundle: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> int:
        """Import a bundle produced by :meth:`export_store`.

        Returns the number of projects imported. Refuses to clobber an existing
        project unless *overwrite* is set, so an accidental import cannot
        silently destroy a ledger.

        Records are written verbatim at the payload level, so a bundle produced
        by another build keeps fields this one does not understand.
        """
        validate_bundle(bundle)

        imported = 0
        for entry in bundle["projects"]:
            key = str(entry["project"]["key"]).upper()

            if not overwrite and await self._store.load_project_payload(key) is not None:
                raise ValidationError(
                    f"Project {key!r} already exists; pass overwrite to replace it",
                    field="project",
                )

            await self._store.save_project_payload(key, entry["project"])
            await self._store.save_issue_payloads(key, entry.get("issues", []))
            await self._store.save_board_payloads(key, entry.get("boards", []))
            imported += 1
        return imported

    # -- Validation -----------------------------------------------------

    async def validate(self) -> dict[str, Any]:
        """Check that every stored project reads back cleanly.

        Returns a report rather than raising, so an operator can see all the
        problems in a damaged store at once instead of only the first.
        """
        problems: list[str] = []
        projects: list[str] = []

        for key in await self._store.list_project_keys():
            try:
                project = await self._store.load_project(key)
                if project is None:
                    problems.append(f"{key}: project.json missing or unreadable")
                    continue
                issues = await self._store.load_issues(key)
                await self._store.load_boards(key)
            except Exception as exc:  # noqa: BLE001 - report, don't mask
                problems.append(f"{key}: {type(exc).__name__}: {exc}")
                continue

            projects.append(key)
            for issue in issues:
                if not issue.key:
                    problems.append(f"{key}: an issue is missing its key")
                if issue.project_key and issue.project_key.upper() != key:
                    problems.append(
                        f"{key}: issue {issue.key!r} claims project "
                        f"{issue.project_key!r}"
                    )

        return {
            "data_dir": str(self._root),
            "schema_version": await self._store.schema_version(),
            "projects": projects,
            "problems": problems,
            "ok": not problems,
        }


def validate_bundle(bundle: Any) -> None:
    """Validate an export bundle's envelope, raising ``ValidationError``.

    Checks the shape an import depends on. It does not police record contents:
    unknown fields are legitimate and must survive.
    """
    if not isinstance(bundle, dict):
        raise ValidationError("Export bundle must be a JSON object", field="bundle")

    version = bundle.get("anvil_export_version")
    if version != EXPORT_VERSION:
        raise ValidationError(
            f"Unsupported export version {version!r}; expected {EXPORT_VERSION}",
            field="anvil_export_version",
        )

    schema_version = bundle.get("schema_version", SCHEMA_VERSION)
    if not isinstance(schema_version, int) or schema_version > SCHEMA_VERSION:
        raise ValidationError(
            f"Bundle schema_version {schema_version!r} is newer than this "
            f"build supports ({SCHEMA_VERSION})",
            field="schema_version",
        )

    projects = bundle.get("projects")
    if not isinstance(projects, list):
        raise ValidationError("Bundle 'projects' must be a list", field="projects")

    for entry in projects:
        if not isinstance(entry, dict) or not isinstance(entry.get("project"), dict):
            raise ValidationError(
                "Each bundle project needs a 'project' object", field="projects"
            )
        if not entry["project"].get("key"):
            raise ValidationError("Each exported project needs a key", field="project")
