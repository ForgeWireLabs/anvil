# Limitations and threat model

ForgeWire Anvil `0.1.0a0` is a **developer preview**. This document states what
it does not do, and what it does not protect against, so you can decide whether
it fits your situation. It is deliberately blunt: an alpha that oversells itself
costs its users data.

## Release status

This is an alpha. The wire format is documented and migration-tested, but
neither the Python API nor the on-disk schema is under a compatibility promise
yet. Pin an exact version.

## Storage limitations

### Single writer only

The JSON store serialises writes with an in-process `asyncio.Lock`. That lock
protects concurrent tasks **inside one process**. It does not protect against
two processes writing the same ledger.

There is no file locking. Two processes writing the same project concurrently
can interleave a read-modify-write cycle and lose one side's changes. The last
writer wins for the whole file, not per record.

**Do not** point two applications, two CLI invocations, or an application and a
CLI at the same ledger at the same time. A multi-process-capable store (expected
to be SQLite behind the same `IssueStore` protocol) is required before Anvil is
advertised as a stable desktop or long-running service backend.

Individual file writes are atomic (write to a temp file, then `os.replace`), so
a crash mid-write cannot leave a half-written file. That is crash safety, not
concurrency safety — the two are often confused.

### Whole-file reads and writes

Each save rewrites a project's entire `issues.json`. This is fine for the
hundreds-to-thousands of issues a local ledger holds and is a real cost beyond
that. There is no index; searches scan.

### No built-in backup

`anvil export` produces a bundle and `anvil import` restores it, but nothing is
scheduled. Backups are the operator's responsibility.

## Trust model

**Anvil trusts its data directory and everything in it.** The ledger is a set of
plain JSON files owned by the local user. Anvil applies no signing, encryption,
integrity checking, or access control of its own; it inherits exactly the
filesystem permissions of the directory it is pointed at.

The consequences are worth stating explicitly:

- Anyone who can read the data directory can read every issue, comment, and
  relation, including anything you put in `metadata` or `custom_fields`.
- Anyone who can write the data directory can forge or alter any record,
  including the activity log. **The activity log is a convenience history, not
  an audit trail**, and must not be relied on as evidence of what happened.
- `anvil import` executes no code, but it does trust the bundle's contents. Only
  import bundles you produced or otherwise trust; the envelope is validated, the
  records are not policed.

If you need integrity or provenance guarantees for execution, that is Fabric's
signed execution log, not Anvil. Anvil relates to execution records; it is not
the execution authority.

## Secrets

**Do not put secrets in a ledger.** No Anvil field is a safe place for API keys,
tokens, passwords, session cookies, bearer material, signed one-time URLs, or
private customer data. Records are stored in cleartext, are included verbatim in
exports, and are surfaced by the CLI.

`IssueRelation.metadata` is the field most likely to be misused this way, since
it accepts arbitrary values. It is for non-secret routing and provenance only.
Anvil itself does not filter metadata; ForgeWire applies its own secret
filtering before writing relations, and that filtering is ForgeWire's, not part
of this package. If you embed Anvil directly, you own that check.

`url` fields must not carry credentials or secret-bearing query strings.

## Relation-field compatibility

`Issue.relations` is the forward canonical field. `Issue.typed_links` is a
compatibility read window over the same records and is still written as a mirror,
so downlevel readers keep working. Legacy `typed_links`-only data is upgraded by
`anvil migrate relations`, which is lossless and idempotent.

The deprecation of `typed_links` has not been scheduled. It will not be removed
without a migration path and a stated window.

## Scale and scope

Not in this release:

- multi-process or networked access;
- multi-user or team synchronisation;
- permissions, roles, or per-record access control;
- a UI;
- full Jira behavioural parity (an optional adapter exists in ForgeWire, not here);
- automatic backup, retention, or compaction.

## Platform

Tested on Windows against CPython 3.11, 3.12, and 3.13. The macOS and Linux data
directory conventions are implemented and unit-tested, but the package has not
yet been exercised end-to-end on those platforms.

## Reporting a problem

Anvil is developed in a private monorepo and published here as a mirror; the
mirror does not accept pull requests. Please open an issue describing the
problem. For anything with a security dimension, do not include real secrets or
customer data in the report.
