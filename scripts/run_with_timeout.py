"""Run a command with a hard timeout and clear failure output."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command with a timeout.")
    parser.add_argument("timeout_seconds", type=float, help="Timeout in seconds.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("command is required")
    return args


def main() -> int:
    args = parse_args()
    command = [str(part) for part in args.command]
    if os.name == "nt":
        process: subprocess.Popen[bytes] = subprocess.Popen(
            command,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        process = subprocess.Popen(command, start_new_session=True)

    try:
        return int(process.wait(timeout=args.timeout_seconds))
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        printable_command = " ".join(command)
        print(
            f"Command timed out after {args.timeout_seconds:g}s: {printable_command}",
            file=sys.stderr,
        )
        return 124


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate the process tree so timed-out child commands cannot linger."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        return

    try:
        process.kill()
    except ProcessLookupError:
        return
    kill_process_group(process.pid, signal.SIGTERM)
    process.wait(timeout=5)


def kill_process_group(pid: int, sig: int) -> None:
    """Kill a POSIX process group; isolated for platforms where killpg is absent."""
    try:
        killpg = getattr(os, "killpg")
    except AttributeError:  # pragma: no cover - Windows branch returns before this.
        return
    try:
        killpg(pid, sig)
    except ProcessLookupError:
        return


if __name__ == "__main__":
    raise SystemExit(main())
