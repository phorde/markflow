"""Run a command with a hard timeout and clear failure output."""

from __future__ import annotations

import argparse
import os
import signal
import shutil
import subprocess  # nosec B404
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


def resolve_command_executable(command: list[str]) -> list[str]:
    """Resolve command executable to absolute path when discoverable."""
    if not command:
        return command

    executable = command[0]
    if os.path.isabs(executable):
        return command

    resolved = shutil.which(executable)
    if not resolved:
        return command
    return [resolved, *command[1:]]


def main() -> int:
    args = parse_args()
    command = resolve_command_executable([str(part) for part in args.command])
    if os.name == "nt":
        creation_flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        process: subprocess.Popen[bytes] = subprocess.Popen(  # nosec B603
            command,
            creationflags=creation_flags,
        )
    else:
        process = subprocess.Popen(  # nosec B603
            command,
            start_new_session=True,
        )

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
        taskkill = shutil.which("taskkill")
        if not taskkill:
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            taskkill = os.path.join(system_root, "System32", "taskkill.exe")
        subprocess.run(
            [taskkill, "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )  # nosec B603
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - rare OS-level race
            process.kill()
            process.wait(timeout=5)
        return

    kill_process_group(process.pid, int(signal.SIGTERM))
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - rare OS-level race
        sigkill = int(getattr(signal, "SIGKILL", signal.SIGTERM))
        kill_process_group(process.pid, sigkill)
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
