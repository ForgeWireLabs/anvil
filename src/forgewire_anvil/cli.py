"""The ``anvil`` command-line interface.

Built on stdlib ``argparse`` so the package stays dependency-free.

Output is human-readable by default and machine-readable with ``--json``.
Exit codes are part of the contract: ``0`` success, ``1`` a planning-domain
error (the exception's stable ``error_code`` is reported), ``2`` a usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Sequence

from .exceptions import IssueTrackerError
from .serialization import (board_to_dict, issue_to_dict, project_to_dict,
                            sprint_to_dict)
from .service import Anvil
from .models import IssueLink, IssueRelation, User

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _emit(args: argparse.Namespace, payload: Any, human: str) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(human)


def _issue_line(issue: Any) -> str:
    return f"{issue.key}  [{issue.status}] {issue.summary}"


def _user(spec: str | None) -> User | None:
    """Parse ``id`` or ``id:Display Name`` into a User."""
    if not spec:
        return None
    user_id, _, display = spec.partition(":")
    return User(id=user_id, display_name=display or user_id)


def _kv(pairs: Sequence[str] | None) -> dict[str, Any]:
    """Parse repeated ``key=value`` options into a dict."""
    out: dict[str, Any] = {}
    for item in pairs or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"error: expected key=value, got {item!r}")
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def _cmd_project_create(anvil: Anvil, args: argparse.Namespace) -> int:
    project = await anvil.provider.create_project(
        key=args.key, name=args.name, description=args.description,
        lead=_user(args.lead), board_type=args.board_type,
    )
    _emit(args, project_to_dict(project), f"Created project {project.key} - {project.name}")
    return EXIT_OK


async def _cmd_project_list(anvil: Anvil, args: argparse.Namespace) -> int:
    projects = await anvil.provider.list_projects()
    _emit(
        args,
        [project_to_dict(p) for p in projects],
        "\n".join(f"{p.key}  {p.name}" for p in projects) or "No projects.",
    )
    return EXIT_OK


async def _cmd_project_get(anvil: Anvil, args: argparse.Namespace) -> int:
    project = await anvil.provider.get_project(args.key)
    _emit(args, project_to_dict(project), f"{project.key}  {project.name}")
    return EXIT_OK


async def _cmd_project_delete(anvil: Anvil, args: argparse.Namespace) -> int:
    await anvil.provider.delete_project(args.key)
    _emit(args, {"deleted": args.key}, f"Deleted project {args.key}")
    return EXIT_OK


async def _cmd_issue_create(anvil: Anvil, args: argparse.Namespace) -> int:
    issue = await anvil.provider.create_issue(
        project_key=args.project, summary=args.summary,
        description=args.description, issue_type=args.type,
        priority=args.priority, assignee=_user(args.assignee),
        labels=args.label, components=args.component,
        parent_key=args.parent, sprint_id=args.sprint,
        story_points=args.story_points, due_date=args.due_date,
        custom_fields=_kv(args.field),
    )
    _emit(args, issue_to_dict(issue), f"Created {issue.key} - {issue.summary}")
    return EXIT_OK


async def _cmd_issue_get(anvil: Anvil, args: argparse.Namespace) -> int:
    issue = await anvil.provider.get_issue(args.key)
    _emit(args, issue_to_dict(issue), _issue_line(issue))
    return EXIT_OK


async def _cmd_issue_update(anvil: Anvil, args: argparse.Namespace) -> int:
    issue = await anvil.provider.update_issue(
        args.key, summary=args.summary, description=args.description,
        priority=args.priority, assignee=_user(args.assignee),
        labels=args.label, components=args.component, sprint_id=args.sprint,
        story_points=args.story_points, due_date=args.due_date,
        custom_fields=_kv(args.field) or None,
    )
    _emit(args, issue_to_dict(issue), f"Updated {issue.key}")
    return EXIT_OK


async def _cmd_issue_delete(anvil: Anvil, args: argparse.Namespace) -> int:
    await anvil.provider.delete_issue(args.key)
    _emit(args, {"deleted": args.key}, f"Deleted {args.key}")
    return EXIT_OK


async def _cmd_search(anvil: Anvil, args: argparse.Namespace) -> int:
    result = await anvil.provider.search_issues(
        project_key=args.project, status=args.status, assignee_id=args.assignee,
        labels=args.label, text=args.text, offset=args.offset, limit=args.limit,
    )
    _emit(
        args,
        {
            "total": result.total, "offset": result.offset, "limit": result.limit,
            "issues": [issue_to_dict(i) for i in result.issues],
        },
        "\n".join(_issue_line(i) for i in result.issues)
        + f"\n({len(result.issues)} of {result.total})" if result.issues
        else "No matching issues.",
    )
    return EXIT_OK


async def _cmd_transitions(anvil: Anvil, args: argparse.Namespace) -> int:
    transitions = await anvil.provider.get_transitions(args.key)
    _emit(
        args,
        [{"name": t.name, "to_status": t.to_status} for t in transitions],
        "\n".join(f"{t.to_status}  ({t.name})" for t in transitions)
        or "No transitions available.",
    )
    return EXIT_OK


async def _cmd_transition(anvil: Anvil, args: argparse.Namespace) -> int:
    issue = await anvil.provider.transition_issue(args.key, args.to_status)
    _emit(args, issue_to_dict(issue), f"{issue.key} -> {issue.status}")
    return EXIT_OK


async def _cmd_comment_add(anvil: Anvil, args: argparse.Namespace) -> int:
    comment = await anvil.provider.add_comment(
        args.key, args.body, author=_user(args.author)
    )
    _emit(args, {"id": comment.id, "body": comment.body}, f"Added comment {comment.id}")
    return EXIT_OK


async def _cmd_board_list(anvil: Anvil, args: argparse.Namespace) -> int:
    boards = await anvil.provider.list_boards(project_key=args.project)
    _emit(
        args,
        [board_to_dict(b) for b in boards],
        "\n".join(f"{b.id}  {b.name}  [{b.board_type}]" for b in boards) or "No boards.",
    )
    return EXIT_OK


async def _cmd_board_get(anvil: Anvil, args: argparse.Namespace) -> int:
    board = await anvil.provider.get_board(args.id)
    _emit(args, board_to_dict(board), f"{board.id}  {board.name}")
    return EXIT_OK


async def _cmd_sprint_create(anvil: Anvil, args: argparse.Namespace) -> int:
    sprint = await anvil.provider.create_sprint(
        board_id=args.board, name=args.name, start_date=args.start,
        end_date=args.end, goal=args.goal,
    )
    _emit(args, sprint_to_dict(sprint), f"Created sprint {sprint.id} - {sprint.name}")
    return EXIT_OK


async def _cmd_sprint_start(anvil: Anvil, args: argparse.Namespace) -> int:
    sprint = await anvil.provider.start_sprint(args.id)
    _emit(args, sprint_to_dict(sprint), f"Sprint {sprint.id} is {sprint.state}")
    return EXIT_OK


async def _cmd_sprint_close(anvil: Anvil, args: argparse.Namespace) -> int:
    sprint = await anvil.provider.close_sprint(args.id)
    _emit(args, sprint_to_dict(sprint), f"Sprint {sprint.id} is {sprint.state}")
    return EXIT_OK


async def _cmd_link_add(anvil: Anvil, args: argparse.Namespace) -> int:
    link = await anvil.provider.add_link(args.key, IssueLink(
        link_type=args.type, source_key=args.key, target_key=args.target,
    ))
    _emit(
        args,
        {"id": link.id, "link_type": link.link_type, "target_key": link.target_key},
        f"Linked {args.key} {link.link_type} {link.target_key}",
    )
    return EXIT_OK


async def _cmd_link_remove(anvil: Anvil, args: argparse.Namespace) -> int:
    await anvil.provider.remove_link(args.key, args.id)
    _emit(args, {"removed": args.id}, f"Removed link {args.id}")
    return EXIT_OK


async def _cmd_relation_add(anvil: Anvil, args: argparse.Namespace) -> int:
    relation = await anvil.provider.add_relation(args.key, IssueRelation(
        source_key=args.key, target_type=args.target_type, target_id=args.target_id,
        target_label=args.label, url=args.url, metadata=_kv(args.meta),
    ))
    _emit(
        args,
        {"id": relation.id, "target_type": relation.target_type,
         "target_id": relation.target_id},
        f"Related {args.key} -> {relation.target_type}:{relation.target_id}",
    )
    return EXIT_OK


async def _cmd_relation_list(anvil: Anvil, args: argparse.Namespace) -> int:
    relations = await anvil.provider.list_relations(args.key)
    _emit(
        args,
        [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id,
          "target_label": r.target_label, "url": r.url} for r in relations],
        "\n".join(f"{r.id}  {r.target_type}:{r.target_id}" for r in relations)
        or "No relations.",
    )
    return EXIT_OK


async def _cmd_relation_remove(anvil: Anvil, args: argparse.Namespace) -> int:
    await anvil.provider.remove_relation(args.key, args.id)
    _emit(args, {"removed": args.id}, f"Removed relation {args.id}")
    return EXIT_OK


async def _cmd_export(anvil: Anvil, args: argparse.Namespace) -> int:
    bundle = await anvil.export_store(project_key=args.project)
    text = json.dumps(bundle, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        if not args.json:
            print(f"Exported {len(bundle['projects'])} project(s) to {args.output}")
        else:
            print(json.dumps({"exported": len(bundle["projects"]), "output": args.output}))
    else:
        print(text)
    return EXIT_OK


async def _cmd_import(anvil: Anvil, args: argparse.Namespace) -> int:
    with open(args.input, encoding="utf-8") as fh:
        bundle = json.load(fh)
    count = await anvil.import_store(bundle, overwrite=args.overwrite)
    _emit(args, {"imported": count}, f"Imported {count} project(s)")
    return EXIT_OK


async def _cmd_validate(anvil: Anvil, args: argparse.Namespace) -> int:
    report = await anvil.validate()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"data_dir: {report['data_dir']}")
        print(f"schema_version: {report['schema_version']}")
        print(f"projects: {len(report['projects'])}")
        if report["problems"]:
            print("problems:")
            for problem in report["problems"]:
                print(f"  - {problem}")
        else:
            print("ok: no problems found")
    return EXIT_OK if report["ok"] else EXIT_ERROR


async def _cmd_migrate_relations(anvil: Anvil, args: argparse.Namespace) -> int:
    changed = await anvil.migrate(project_key=args.project)
    _emit(args, {"changed": changed}, f"Canonicalized relations on {changed} issue(s)")
    return EXIT_OK


async def _cmd_migrate_store(anvil: Anvil, args: argparse.Namespace) -> int:
    count = await anvil.migrate_from(args.source, overwrite=args.overwrite)
    _emit(
        args,
        {"migrated": count, "source": args.source, "destination": str(anvil.data_dir)},
        f"Migrated {count} project(s) from {args.source} into {anvil.data_dir}",
    )
    return EXIT_OK


async def _cmd_info(anvil: Anvil, args: argparse.Namespace) -> int:
    payload = {
        "data_dir": str(anvil.data_dir),
        "schema_version": await anvil.schema_version(),
        "projects": await anvil.store.list_project_keys(),
    }
    _emit(
        args, payload,
        f"data_dir: {payload['data_dir']}\n"
        f"schema_version: {payload['schema_version']}\n"
        f"projects: {', '.join(payload['projects']) or '(none)'}",
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anvil",
        description="ForgeWire Anvil - the local-first planning ledger.",
    )
    parser.add_argument(
        "--data-dir",
        help="Ledger location (overrides ANVIL_DATA_DIR and the user default).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text."
    )
    sub = parser.add_subparsers(dest="command")

    # -- info ----------------------------------------------------------
    info = sub.add_parser("info", help="Show the ledger location and schema version.")
    info.set_defaults(func=_cmd_info)

    # -- project -------------------------------------------------------
    project = sub.add_parser("project", help="Manage projects.")
    project_sub = project.add_subparsers(dest="subcommand")

    p_create = project_sub.add_parser("create", help="Create a project.")
    p_create.add_argument("key")
    p_create.add_argument("name")
    p_create.add_argument("--description")
    p_create.add_argument("--lead", help="User as 'id' or 'id:Display Name'.")
    p_create.add_argument("--board-type", default="kanban", choices=["kanban", "scrum"])
    p_create.set_defaults(func=_cmd_project_create)

    p_list = project_sub.add_parser("list", help="List projects.")
    p_list.set_defaults(func=_cmd_project_list)

    p_get = project_sub.add_parser("get", help="Show a project.")
    p_get.add_argument("key")
    p_get.set_defaults(func=_cmd_project_get)

    p_delete = project_sub.add_parser("delete", help="Delete a project and its issues.")
    p_delete.add_argument("key")
    p_delete.set_defaults(func=_cmd_project_delete)

    # -- issue ---------------------------------------------------------
    issue = sub.add_parser("issue", help="Manage issues.")
    issue_sub = issue.add_subparsers(dest="subcommand")

    i_create = issue_sub.add_parser("create", help="Create an issue.")
    i_create.add_argument("project")
    i_create.add_argument("summary")
    i_create.add_argument("--description")
    i_create.add_argument("--type", default="task")
    i_create.add_argument("--priority", default="medium")
    i_create.add_argument("--assignee", help="User as 'id' or 'id:Display Name'.")
    i_create.add_argument("--label", action="append")
    i_create.add_argument("--component", action="append")
    i_create.add_argument("--parent")
    i_create.add_argument("--sprint")
    i_create.add_argument("--story-points", type=float)
    i_create.add_argument("--due-date")
    i_create.add_argument("--field", action="append", metavar="KEY=VALUE")
    i_create.set_defaults(func=_cmd_issue_create)

    i_get = issue_sub.add_parser("get", help="Show an issue.")
    i_get.add_argument("key")
    i_get.set_defaults(func=_cmd_issue_get)

    i_update = issue_sub.add_parser("update", help="Update an issue.")
    i_update.add_argument("key")
    i_update.add_argument("--summary")
    i_update.add_argument("--description")
    i_update.add_argument("--priority")
    i_update.add_argument("--assignee")
    i_update.add_argument("--label", action="append")
    i_update.add_argument("--component", action="append")
    i_update.add_argument("--sprint")
    i_update.add_argument("--story-points", type=float)
    i_update.add_argument("--due-date")
    i_update.add_argument("--field", action="append", metavar="KEY=VALUE")
    i_update.set_defaults(func=_cmd_issue_update)

    i_delete = issue_sub.add_parser("delete", help="Delete an issue.")
    i_delete.add_argument("key")
    i_delete.set_defaults(func=_cmd_issue_delete)

    # -- search --------------------------------------------------------
    search = sub.add_parser("search", help="Search issues.")
    search.add_argument("--project")
    search.add_argument("--status")
    search.add_argument("--assignee", dest="assignee")
    search.add_argument("--label", action="append")
    search.add_argument("--text")
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--limit", type=int, default=50)
    search.set_defaults(func=_cmd_search)

    # -- transitions ---------------------------------------------------
    transitions = sub.add_parser("transitions", help="List legal transitions.")
    transitions.add_argument("key")
    transitions.set_defaults(func=_cmd_transitions)

    transition = sub.add_parser("transition", help="Move an issue to a status.")
    transition.add_argument("key")
    transition.add_argument("to_status")
    transition.set_defaults(func=_cmd_transition)

    # -- comment -------------------------------------------------------
    comment = sub.add_parser("comment", help="Comment on an issue.")
    comment_sub = comment.add_subparsers(dest="subcommand")
    c_add = comment_sub.add_parser("add", help="Add a comment.")
    c_add.add_argument("key")
    c_add.add_argument("body")
    c_add.add_argument("--author")
    c_add.set_defaults(func=_cmd_comment_add)

    # -- board ---------------------------------------------------------
    board = sub.add_parser("board", help="Inspect boards.")
    board_sub = board.add_subparsers(dest="subcommand")
    b_list = board_sub.add_parser("list", help="List boards.")
    b_list.add_argument("--project")
    b_list.set_defaults(func=_cmd_board_list)
    b_get = board_sub.add_parser("get", help="Show a board.")
    b_get.add_argument("id")
    b_get.set_defaults(func=_cmd_board_get)

    # -- sprint --------------------------------------------------------
    sprint = sub.add_parser("sprint", help="Manage sprints.")
    sprint_sub = sprint.add_subparsers(dest="subcommand")
    s_create = sprint_sub.add_parser("create", help="Create a sprint.")
    s_create.add_argument("board")
    s_create.add_argument("name")
    s_create.add_argument("--start")
    s_create.add_argument("--end")
    s_create.add_argument("--goal")
    s_create.set_defaults(func=_cmd_sprint_create)
    s_start = sprint_sub.add_parser("start", help="Start a sprint.")
    s_start.add_argument("id")
    s_start.set_defaults(func=_cmd_sprint_start)
    s_close = sprint_sub.add_parser("close", help="Close a sprint.")
    s_close.add_argument("id")
    s_close.set_defaults(func=_cmd_sprint_close)

    # -- link (issue-to-issue) ------------------------------------------
    link = sub.add_parser("link", help="Link one issue to another.")
    link_sub = link.add_subparsers(dest="subcommand")
    l_add = link_sub.add_parser("add", help="Add an issue-to-issue link.")
    l_add.add_argument("key")
    l_add.add_argument("target")
    l_add.add_argument("--type", default="relates_to")
    l_add.set_defaults(func=_cmd_link_add)
    l_remove = link_sub.add_parser("remove", help="Remove an issue-to-issue link.")
    l_remove.add_argument("key")
    l_remove.add_argument("id")
    l_remove.set_defaults(func=_cmd_link_remove)

    # -- relation (issue-to-work-object) --------------------------------
    relation = sub.add_parser("relation", help="Relate an issue to a work object.")
    relation_sub = relation.add_subparsers(dest="subcommand")
    r_add = relation_sub.add_parser("add", help="Add a typed relation.")
    r_add.add_argument("key")
    r_add.add_argument("target_type")
    r_add.add_argument("target_id")
    r_add.add_argument("--label")
    r_add.add_argument("--url")
    r_add.add_argument("--meta", action="append", metavar="KEY=VALUE")
    r_add.set_defaults(func=_cmd_relation_add)
    r_list = relation_sub.add_parser("list", help="List typed relations.")
    r_list.add_argument("key")
    r_list.set_defaults(func=_cmd_relation_list)
    r_remove = relation_sub.add_parser("remove", help="Remove a typed relation.")
    r_remove.add_argument("key")
    r_remove.add_argument("id")
    r_remove.set_defaults(func=_cmd_relation_remove)

    # -- export / import / validate / migrate ---------------------------
    export = sub.add_parser("export", help="Export the ledger as a JSON bundle.")
    export.add_argument("--project", help="Export only this project.")
    export.add_argument("--output", "-o", help="Write to a file instead of stdout.")
    export.set_defaults(func=_cmd_export)

    imp = sub.add_parser("import", help="Import a JSON bundle.")
    imp.add_argument("input")
    imp.add_argument("--overwrite", action="store_true",
                     help="Replace projects that already exist.")
    imp.set_defaults(func=_cmd_import)

    validate = sub.add_parser("validate", help="Check that the ledger reads cleanly.")
    validate.set_defaults(func=_cmd_validate)

    migrate = sub.add_parser("migrate", help="Migrate ledger data.")
    migrate_sub = migrate.add_subparsers(dest="subcommand")

    m_relations = migrate_sub.add_parser(
        "relations",
        help="Canonicalize legacy typed_links onto the relations field.",
    )
    m_relations.add_argument("--project")
    m_relations.set_defaults(func=_cmd_migrate_relations)

    m_store = migrate_sub.add_parser(
        "store",
        help="Adopt a ledger from another directory, such as a legacy "
             "data/issue_tracker layout, into this one.",
    )
    m_store.add_argument("source", help="Directory holding the existing ledger.")
    m_store.add_argument("--overwrite", action="store_true",
                         help="Replace projects that already exist here.")
    m_store.set_defaults(func=_cmd_migrate_store)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> int:
    anvil = Anvil(args.data_dir)
    try:
        return await args.func(anvil, args)
    finally:
        await anvil.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return asyncio.run(_run(args))
    except IssueTrackerError as exc:
        code = exc.error_code or "ERROR"
        print(f"error [{code}]: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
