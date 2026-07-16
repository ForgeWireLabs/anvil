# Changelog

All notable changes to ForgeWire Anvil are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While
the version is `0.x` / alpha, the Python API and the on-disk schema may change
between releases; pin an exact version.

## [Unreleased]

## [0.1.0a0] — 2026-07-16

First developer preview, extracted from the ForgeWire monorepo's
`core/services/issue_tracker` tree. Behavior is preserved from that
implementation rather than reinvented, so existing Anvil ledgers keep working.

### Added

- **Domain core** — projects, issues, boards, sprints, comments, activity
  history, issue-to-issue links, and typed provider-neutral relations, with a
  provider-neutral enum vocabulary and workflow contract.
- **Exceptions** — a planning-domain hierarchy with stable `error_code` strings.
- **Protocols** — `IssueTrackerProvider` and `IssueStore`, both
  `runtime_checkable`, so providers and storage backends are swappable.
- **`AnvilProvider`** — the built-in offline provider.
- **`AnvilStore`** — the JSON file store: one directory per project, atomic
  temp-and-rename writes, and preservation of unknown and legacy record fields
  on round trip.
- **Schema versioning** — a `.anvil-store.json` marker at the store root. A store
  with no marker is treated as the baseline version rather than as corrupt, and a
  marker is only ever added, never silently rewritten.
- **Relation canonicalization** — `Issue.relations` is the forward canonical
  field; `Issue.typed_links` is retained as a compatibility read window and
  written as a mirror. `anvil migrate relations` upgrades legacy
  `typed_links`-only data losslessly and idempotently.
- **`Anvil` service facade** — data-directory wiring plus export, import,
  validation, and migration. It raises the typed exception hierarchy rather than
  wrapping results, so an embedding application maps errors once at its own
  boundary.
- **User-scoped data directory** — resolved as explicit path, then
  `ANVIL_DATA_DIR`, then a platform default (`%LOCALAPPDATA%\ForgeWire\Anvil`,
  `~/Library/Application Support/ForgeWire/Anvil`, or
  `$XDG_DATA_HOME/forgewire/anvil`). There is deliberately no
  working-directory-relative default.
- **`anvil` CLI** — the full surface (`info`, `project`, `issue`, `search`,
  `transitions`, `transition`, `comment`, `board`, `sprint`, `link`, `relation`,
  `export`, `import`, `validate`, `migrate relations`, `migrate store`), with
  `--data-dir`, `--json`, and contract exit codes: `0` success, `1` a
  planning-domain error (its stable code printed to stderr), `2` usage.
- **`anvil migrate store`** — adopts a ledger from another directory, the upgrade
  path off a legacy working-directory-relative `data/issue_tracker` layout. The
  source is only read, never modified.
- **Apache-2.0 licence**, `py.typed`, and no runtime dependencies.

### Notes

- Export and import operate on stored records verbatim rather than round-tripping
  through the models, so fields this build does not know about survive a backup
  and restore.
- The JSON store is single-writer. See [docs/limitations.md](docs/limitations.md)
  before pointing more than one process at a ledger.

[Unreleased]: https://github.com/ForgeWireLabs/anvil/compare/v0.1.0a0...HEAD
[0.1.0a0]: https://github.com/ForgeWireLabs/anvil/releases/tag/v0.1.0a0
