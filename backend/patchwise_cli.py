from __future__ import annotations

import argparse
import json
import sys

from pw_cli.runner import continue_with_user_input_sync, resume_session_sync, run_new_session_sync
from pw_cli.store import CLISessionStore


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _emit_result(result) -> None:
    _print_json(
        {
            "session_id": result.session_id,
            "status": result.status,
            "verdict": result.verdict,
            "current_round": result.current_round,
            "max_rounds": result.max_rounds,
            "summary": result.summary,
        }
    )


def _result_exit_code(result) -> int:
    if result.verdict == "LGTM":
        return 0
    if result.status == "waiting_user":
        return 3
    if result.verdict in {"NEEDS_WORK", "MAX_ROUNDS", "BLOCKED"}:
        return 2
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    result = run_new_session_sync(
        store,
        input_value=args.input,
        input_type=args.input_type,
        subsystem=args.subsystem,
        source_path=args.source_path,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        max_rounds=args.max_rounds,
    )
    _emit_result(result)
    return _result_exit_code(result)


def cmd_status(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    session = store.get_session(args.session)
    if not session:
        print(f"Session not found: {args.session}", file=sys.stderr)
        return 1
    _print_json(
        {
            "session_id": session.session_id,
            "status": session.status,
            "input_type": session.input_type,
            "input_ref": session.input_ref,
            "subsystem": session.subsystem,
            "current_round": session.current_round,
            "max_rounds": session.max_rounds,
            "verdict": session.verdict,
            "summary": session.summary,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    session = store.get_session(args.session)
    if not session:
        print(f"Session not found: {args.session}", file=sys.stderr)
        return 1

    rounds = store.get_rounds(args.session, round_num=args.round)
    if not args.include_state:
        for item in rounds:
            item.pop("state", None)
    messages = store.get_messages(args.session, limit=args.message_limit)
    payload = {
        "session": {
            "session_id": session.session_id,
            "status": session.status,
            "verdict": session.verdict,
            "current_round": session.current_round,
            "max_rounds": session.max_rounds,
            "summary": session.summary,
        },
        "rounds": rounds,
        "messages": messages,
    }
    _print_json(payload)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    sessions = store.list_sessions(limit=args.limit)
    _print_json({"sessions": sessions})
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    try:
        result = resume_session_sync(store, args.session)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_result(result)
    return _result_exit_code(result)


def cmd_clarify(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    try:
        result = continue_with_user_input_sync(
            store,
            session_id=args.session,
            response=args.response,
            mode="clarify",
            override_decision="resume",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_result(result)
    return _result_exit_code(result)


def cmd_respond(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    try:
        result = continue_with_user_input_sync(
            store,
            session_id=args.session,
            response=args.response,
            mode="respond",
            override_decision="resume",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_result(result)
    return _result_exit_code(result)


def cmd_override(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    try:
        result = continue_with_user_input_sync(
            store,
            session_id=args.session,
            response=args.note or "",
            mode="override",
            override_decision=args.decision,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_result(result)
    return _result_exit_code(result)


def cmd_kb(args: argparse.Namespace) -> int:
    store = CLISessionStore(db_path=args.db_path)
    action = args.action
    if action == "stats":
        _print_json({"kb": store.kb_stats()})
        return 0
    if action == "audit":
        patterns = store.list_kb_patterns(subsystem=args.subsystem, limit=args.limit)
        _print_json({"patterns": patterns})
        return 0
    if action == "promote":
        ok = store.set_pattern_state(args.pattern_key, "promoted")
        _print_json({"pattern_key": args.pattern_key, "state": "promoted", "updated": bool(ok)})
        return 0 if ok else 1
    if action == "rollback":
        ok = store.set_pattern_state(args.pattern_key, "deprecated")
        _print_json({"pattern_key": args.pattern_key, "state": "deprecated", "updated": bool(ok)})
        return 0 if ok else 1
    print(f"Unsupported kb action: {action}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PatchWise CLI-first A2A runner")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override SQLite DB path for CLI sessions",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Start a new CLI A2A review session")
    run.add_argument("--input", required=True, help="Raw patch text, file path, or URL")
    run.add_argument(
        "--input-type",
        default="auto",
        choices=["auto", "raw", "file"],
        help="Input mode. auto uses URL/file detection",
    )
    run.add_argument("--subsystem", default="audio", help="Subsystem context")
    run.add_argument("--source-path", default="", help="Kernel source path hint")
    run.add_argument("--llm-provider", default="qgenie", help="LLM provider")
    run.add_argument("--llm-model", default="gpt-4o", help="LLM model")
    run.add_argument("--max-rounds", type=int, default=5, help="Maximum A2A rounds")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="Show status for a CLI session")
    status.add_argument("--session", required=True, help="Session ID")
    status.set_defaults(func=cmd_status)

    show = sub.add_parser("show", help="Show rounds and messages for a session")
    show.add_argument("--session", required=True, help="Session ID")
    show.add_argument("--round", type=int, default=None, help="Filter to one round")
    show.add_argument("--message-limit", type=int, default=200, help="Max messages to return")
    show.add_argument(
        "--include-state",
        action="store_true",
        help="Include full per-round state payloads",
    )
    show.set_defaults(func=cmd_show)

    history = sub.add_parser("history", help="List recent CLI sessions")
    history.add_argument("--limit", type=int, default=20, help="Number of sessions")
    history.set_defaults(func=cmd_history)

    resume = sub.add_parser("resume", help="Resume an existing CLI session")
    resume.add_argument("--session", required=True, help="Session ID")
    resume.set_defaults(func=cmd_resume)

    clarify = sub.add_parser("clarify", help="Provide clarification and continue waiting session")
    clarify.add_argument("--session", required=True, help="Session ID")
    clarify.add_argument("--response", required=True, help="Clarification text for both agents")
    clarify.set_defaults(func=cmd_clarify)

    respond = sub.add_parser("respond", help="Alias of clarify")
    respond.add_argument("--session", required=True, help="Session ID")
    respond.add_argument("--response", required=True, help="Response text")
    respond.set_defaults(func=cmd_respond)

    override = sub.add_parser("override", help="Override blocked session verdict or resume")
    override.add_argument("--session", required=True, help="Session ID")
    override.add_argument(
        "--decision",
        required=True,
        choices=["resume", "approve", "needs_work"],
        help="resume clears block and reruns; approve/needs_work finalize session",
    )
    override.add_argument("--note", default="", help="Optional operator note")
    override.set_defaults(func=cmd_override)

    kb = sub.add_parser("kb", help="Knowledge-base commands (phase 3)")
    kb_sub = kb.add_subparsers(dest="action", required=True)
    kb_stats = kb_sub.add_parser("stats", help="Show KB stats")
    kb_stats.set_defaults(func=cmd_kb)
    kb_audit = kb_sub.add_parser("audit", help="List KB patterns")
    kb_audit.add_argument("--subsystem", default=None, help="Optional subsystem filter")
    kb_audit.add_argument("--limit", type=int, default=50, help="Maximum patterns")
    kb_audit.set_defaults(func=cmd_kb)
    kb_promote = kb_sub.add_parser("promote", help="Force-promote a pattern")
    kb_promote.add_argument("--pattern-key", required=True, help="Pattern key")
    kb_promote.set_defaults(func=cmd_kb)
    kb_rollback = kb_sub.add_parser("rollback", help="Deprecate a pattern")
    kb_rollback.add_argument("--pattern-key", required=True, help="Pattern key")
    kb_rollback.set_defaults(func=cmd_kb)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
