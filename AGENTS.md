# Anvil Agent Contract

Anvil is a local-first, provider-neutral planning ledger. Review the README, documentation, existing tests, and relevant decisions before changes.

- Preserve offline operation, user-owned data, atomic writes, schema/version compatibility, and lossless export/import semantics.
- Respect the documented single-writer store boundary; never claim multi-writer safety without dedicated evidence.
- Test failure/recovery and old-data compatibility for storage or migration changes. Do not replace the existing ledger with a second source of truth.
- Keep planning records distinct from authority to execute external work; avoid unapproved network actions or publication.

<!-- BEGIN SHARED AGENT SELF-AUDIT v1 -->
## Mandatory pre-completion adversarial self-audit

Before claiming completion or requesting review, inspect the full task-scoped change against an explicit review base: committed branch diff, staged and unstaged changes, and relevant untracked files. Record base/HEAD and preserve unrelated user changes. A bare `git diff` is not the whole candidate.

Look for concrete correctness and edge-case defects, concurrency/races, fail-closed behavior, API/schema compatibility, security and authority boundaries, durability, resource leaks/cleanup, missing positive and negative tests, and unnecessary complexity or out-of-scope edits. Tie each finding to a location and credible failure scenario; do not invent stylistic defects or churn working code.

Repair confirmed defects only within authorized scope, rerun affected checks, and reinspect remediation. Use at most two repair/re-review cycles by default; if blocked, report `INCOMPLETE` or `FAIL` instead of looping or weakening tests/invariants. Escalate changes requiring new authority.

Pre-existing failures are not waived by showing they also occur on the baseline. Separate cause attribution from resolution: repair the confirmed root cause when authorized, or create/link an owned, actionable remediation work item with reproduction, evidence, and a validation gate. Preserve failures and keep project-level health accurately red or incomplete until resolved. Never use permanent skips, false evidence, or weakened assertions to manufacture green results.

Handoff must state `Self-Audit: PASS|INCOMPLETE|FAIL`, reviewed revision and scope, concrete findings/fixes (or no confirmed findings), actual checks/results, unrun checks, and residual risks. PASS means review completed with no known in-scope blockers, not proof of defect freedom. Self-review is neither independent approval nor authorization to merge, deploy, release, publish, or perform destructive operations.
<!-- END SHARED AGENT SELF-AUDIT v1 -->
