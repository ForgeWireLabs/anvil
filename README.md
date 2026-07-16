# ForgeWire Anvil

**A local-first planning ledger for human and agentic work.**

Projects, issues, boards, sprints, workflows, and typed relations — provider
neutral, auditable, dependency-free, and fully usable with no network and no
external issue-tracker account.

```bash
pip install forgewire-anvil
```

```bash
anvil project create PF "Platform"
anvil issue create PF "Ship the thing" --priority high --label release
anvil transition PF-1 todo
anvil relation add PF-1 fabric_task task-42 --label "Build"
anvil validate
```

```python
from forgewire_anvil import Anvil, IssueRelation

anvil = Anvil()                      # user-scoped ledger; honors ANVIL_DATA_DIR
await anvil.provider.create_project(key="PF", name="Platform")
issue = await anvil.provider.create_issue(project_key="PF", summary="Ship it")
await anvil.provider.add_relation(issue.key, IssueRelation(
    source_key=issue.key, target_type="fabric_task", target_id="task-42",
))
```

> **Status: developer preview (`0.1.0a0`).** The API and on-disk schema may change
> between releases — pin an exact version. The JSON store is **single-writer**;
> read [docs/limitations.md](https://github.com/ForgeWireLabs/anvil/blob/main/docs/limitations.md) before pointing more than one
> process at a ledger.

## Why

Planning tools assume a server, an account, and a human. Anvil assumes none of
them. It is a ledger you own, on disk, in plain JSON you can read — designed so
agents and people can plan against the same records without a hosted service in
the middle.

Being local-first is the point, not a limitation:

- **Yours.** Plain JSON in a directory you choose. No account, no telemetry, no
  network calls. Ever.
- **Durable.** Atomic writes, schema versioning, and lossless export/import.
  Fields a newer build wrote survive an older build reading and re-saving them.
- **Provider-neutral.** `IssueTrackerProvider` and `IssueStore` are protocols;
  the built-in provider and JSON store are just the default implementations.
- **Dependency-free.** No runtime dependencies. The CLI is stdlib `argparse`.

## What Anvil owns — and what it doesn't

Anvil owns projects, issues, planning lifecycle, workflows and transitions,
boards and sprints, comments and activity history, issue-to-issue links, typed
relations to external work objects, local storage, schema migration, and
import/export.

Anvil does **not** own execution. It links to and summarises execution records;
it is not the execution authority, and its activity log is a convenience history
rather than an audit trail. Signed remote execution, host execution, repository
governance, and approval workflows belong to the systems that own them.

That boundary is the design: *cross-system references are typed relations and
summarised events, never duplicate authoritative records.*

## Where data lives

Resolved in this order:

1. an explicit path (`Anvil("/path")`, or `anvil --data-dir /path`);
2. the `ANVIL_DATA_DIR` environment variable;
3. a per-user platform directory:
   - Windows — `%LOCALAPPDATA%\ForgeWire\Anvil`
   - macOS — `~/Library/Application Support/ForgeWire/Anvil`
   - Linux/BSD — `$XDG_DATA_HOME/forgewire/anvil` (else `~/.local/share/forgewire/anvil`)

There is deliberately no working-directory-relative default: an operational
ledger that follows your shell around scatters itself across checkouts.

Each project is a directory of human-readable JSON:

```text
<data-dir>/
├── .anvil-store.json     # schema version marker
└── PF/
    ├── project.json      # metadata + next-issue counter
    ├── issues.json       # every issue, with comments, links, relations, history
    └── boards.json       # boards, with embedded sprints
```

Already have a ledger somewhere else? `anvil migrate store <source>` adopts it
losslessly and only ever reads the source.

## Errors

Anvil raises; it does not wrap. Every failure is an `IssueTrackerError` subclass
carrying a stable `error_code` (`ISSUE_NOT_FOUND`, `INVALID_TRANSITION`,
`VALIDATION_ERROR`, …), so an embedding application maps errors once at its own
boundary instead of unwrapping a second envelope.

The CLI surfaces the same contract: exit `0` on success, `1` on a
planning-domain error (with its code on stderr), `2` on a usage error. Add
`--json` to any command for machine-readable output.

## Relations vs. typed_links

`Issue.relations` is the forward canonical field for provider-neutral links to
non-issue work objects. `Issue.typed_links` is an earlier name for the same
records, kept as a **compatibility read window** and still written as a mirror,
so downlevel readers keep working. Legacy `typed_links`-only data upgrades via:

```bash
anvil migrate relations
```

The migration is lossless, idempotent, and preserves unknown fields. No
deprecation of `typed_links` is scheduled; it will not be removed without a
migration path and a stated window.

## Development

```bash
pytest                 # no install needed: pyproject sets pythonpath
python -m build
```

Requires Python 3.11+. Tested against CPython 3.11, 3.12, and 3.13.

## Contributing

Anvil is developed in ForgeWire's private monorepo and published here as a
**mirror**, so this repository does not accept pull requests — a sync would
overwrite them. Issues and discussion are welcome and read.

## Licence

[Apache-2.0](https://github.com/ForgeWireLabs/anvil/blob/main/LICENSE).
