"""Thin CLI adapter for the Operator.

All operator methods are exposed via argparse subcommands.
Logic stays in ops.py; this is just a thin request/response mapper.

Uses wiring.py to select persistent vs. in-memory backends based on CLEANROOM_PG_DSN.
"""

import argparse
import dataclasses
import json
import os
import sys

from cleanroom.control.registry.types import TaskSpec
from cleanroom.control.server.wiring import (
    make_operator,
    make_logclient,
    make_dispatch_ctx,
    governance_pore,
)


def main(argv=None):
    """Entry point for CLI. `argv` lets tests drive it without touching sys.argv."""
    parser = argparse.ArgumentParser(description="Control plane CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Initialize operator with persistent or in-memory backends
    operator = make_operator()

    # list_tasks subcommand
    subparsers.add_parser("list-tasks", help="List all active tasks")

    # get_task subcommand
    get_task_parser = subparsers.add_parser("get-task", help="Get task by ID")
    get_task_parser.add_argument("task_id", help="Task ID")

    # register_task subcommand
    register_parser = subparsers.add_parser("register-task", help="Register a new task")
    register_parser.add_argument("--spec-json", required=True, help="Task spec as JSON")

    # dispatch_run subcommand
    dispatch_parser = subparsers.add_parser("dispatch-run", help="Dispatch a run")
    dispatch_parser.add_argument("task_id", help="Task ID")
    dispatch_parser.add_argument("--model", required=True, help="Model name")
    dispatch_parser.add_argument("--iterations", type=int, default=10, help="Iterations")

    # get_run subcommand
    run_parser = subparsers.add_parser("get-run", help="Get run status")
    run_parser.add_argument("run_id", help="Run ID")

    # list_runs subcommand
    subparsers.add_parser("list-runs", help="List all runs")

    # cancel_run subcommand
    cancel_parser = subparsers.add_parser("cancel-run", help="Cancel a run")
    cancel_parser.add_argument("run_id", help="Run ID")

    # pending_escalations subcommand
    subparsers.add_parser(
        "pending-escalations", help="List pending escalations"
    )

    # adjudicate subcommand
    adj_parser = subparsers.add_parser("adjudicate", help="Adjudicate a crossing")
    adj_parser.add_argument("crossing_id", type=int, help="Crossing ID")
    adj_parser.add_argument("decision", help="Decision (approve/reject/allow/block)")
    adj_parser.add_argument("--rationale", help="Optional rationale")
    adj_parser.add_argument("--judge", default="human", help="Judge identifier")

    # read_curve subcommand
    curve_parser = subparsers.add_parser("read-curve", help="Read performance curve")
    curve_parser.add_argument("task_id", help="Task ID")

    # read_boundary subcommand
    subparsers.add_parser("read-boundary", help="Read the boundary instrument (spatial + longitudinal)")

    args = parser.parse_args(argv)

    # Print stderr note if running in-memory (helpful for operator awareness)
    if not os.environ.get("CLEANROOM_PG_DSN"):
        print(
            "[info] CLEANROOM_PG_DSN not set; using in-memory storage (not persistent across processes)",
            file=sys.stderr,
        )

    if args.command == "list-tasks":
        tasks = operator.list_tasks()
        print(json.dumps([dataclasses.asdict(t) for t in tasks], indent=2))

    elif args.command == "get-task":
        task = operator.get_task(args.task_id)
        if task:
            print(json.dumps(dataclasses.asdict(task), indent=2))
        else:
            print(f"Task {args.task_id} not found")

    elif args.command == "register-task":
        try:
            spec_dict = json.loads(args.spec_json)
            spec = TaskSpec(**spec_dict)
            logclient = make_logclient()
            task_id = operator.register_task(
                spec, pore=governance_pore(), logclient=logclient
            )
            result = {
                "task_id": task_id,
                "pending_judgment": (
                    operator.registry.tasks_dir / f"{task_id}.json"
                ).read_text().count("pending_judgment") > 0,
            }
            print(json.dumps(result, indent=2))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"Error: invalid spec JSON: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "dispatch-run":
        logclient = make_logclient()
        ctx = make_dispatch_ctx(logclient)
        run_id = operator.dispatch_run(
            args.task_id, model=args.model, iterations=args.iterations, ctx=ctx
        )
        print(json.dumps({"run_id": run_id}, indent=2))

    elif args.command == "get-run":
        status = operator.get_run(args.run_id)
        if status:
            print(json.dumps(dataclasses.asdict(status), indent=2, default=str))
        else:
            print(f"Run {args.run_id} not found")

    elif args.command == "list-runs":
        runs = operator.list_runs()
        print(json.dumps([dataclasses.asdict(r) for r in runs], indent=2, default=str))

    elif args.command == "cancel-run":
        operator.cancel_run(args.run_id)
        print(json.dumps({"run_id": args.run_id, "state": "cancelled"}, indent=2))

    elif args.command == "pending-escalations":
        logclient = make_logclient()
        escalations = operator.pending_escalations(logclient)
        print(json.dumps(escalations, indent=2, default=str))

    elif args.command == "adjudicate":
        logclient = make_logclient()
        operator.adjudicate(
            args.crossing_id,
            args.decision,
            rationale=args.rationale,
            judge=args.judge,
            logclient=logclient,
        )
        print(
            json.dumps(
                {
                    "crossing_id": args.crossing_id,
                    "decision": args.decision,
                    "judge": args.judge,
                },
                indent=2,
            )
        )

    elif args.command == "read-curve":
        logclient = make_logclient()
        experiments = operator.read_curve(args.task_id, logclient=logclient)
        print(json.dumps(experiments, indent=2, default=str))

    elif args.command == "read-boundary":
        logclient = make_logclient()
        boundary = operator.read_boundary(logclient=logclient)
        print(json.dumps(boundary, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
