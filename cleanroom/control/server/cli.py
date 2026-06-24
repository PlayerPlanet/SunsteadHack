"""Thin CLI adapter for the Operator.

All operator methods are exposed via argparse subcommands.
Logic stays in ops.py; this is just a thin request/response mapper.
"""

import argparse
import json

from cleanroom.control.ops import Operator
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.control.dispatcher.store_interface import InMemoryRunStore
from cleanroom.fixtures import CannedBenchmark, DummyProposer, InMemoryLogClient, NoOpPore


def main():
    """Entry point for CLI."""
    parser = argparse.ArgumentParser(description="Control plane CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Initialize operator from default fixtures
    registry = TaskRegistryStore()
    run_store = InMemoryRunStore()
    operator = Operator(registry, run_store)

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

    # read_curve subcommand
    curve_parser = subparsers.add_parser("read-curve", help="Read performance curve")
    curve_parser.add_argument("task_id", help="Task ID")

    args = parser.parse_args()

    if args.command == "list-tasks":
        tasks = operator.list_tasks()
        print(json.dumps([t.__dict__ for t in tasks], indent=2))

    elif args.command == "get-task":
        task = operator.get_task(args.task_id)
        if task:
            print(json.dumps(task.__dict__, indent=2))
        else:
            print(f"Task {args.task_id} not found")

    elif args.command == "register-task":
        # This is a stub — full implementation would construct TaskSpec from JSON
        print("register-task: not implemented in Phase-0 CLI stub")

    elif args.command == "dispatch-run":
        ctx = {
            "proposer": DummyProposer(),
            "benchmark": CannedBenchmark(),
            "pore": NoOpPore(),
            "logclient": InMemoryLogClient(),
        }
        run_id = operator.dispatch_run(
            args.task_id, model=args.model, iterations=args.iterations, ctx=ctx
        )
        print(f"Dispatched run: {run_id}")

    elif args.command == "get-run":
        status = operator.get_run(args.run_id)
        if status:
            print(json.dumps(status.__dict__, indent=2))
        else:
            print(f"Run {args.run_id} not found")

    elif args.command == "list-runs":
        runs = operator.list_runs()
        print(json.dumps([r.__dict__ for r in runs], indent=2))

    elif args.command == "cancel-run":
        operator.cancel_run(args.run_id)
        print(f"Cancelled run: {args.run_id}")

    elif args.command == "pending-escalations":
        # This is a stub — full implementation would use injected logclient
        print("pending-escalations: not implemented in Phase-0 CLI stub")

    elif args.command == "read-curve":
        # This is a stub — full implementation would use injected logclient
        print("read-curve: not implemented in Phase-0 CLI stub")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
