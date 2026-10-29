"""External-tool execution with bounded time and retained diagnostics."""
from pathlib import Path
import subprocess


def run(command, *, cwd=None, timeout=30, allowed=(0,), log=None):
    command = [str(item) for item in command]
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Timed out after {timeout}s: {command!r}\n{exc.stdout!r}\n{exc.stderr!r}') from exc
    except OSError as exc:
        raise RuntimeError(f'Cannot run {command[0]}: {exc}') from exc
    output = result.stdout + result.stderr
    if log is not None:
        Path(log).write_text(output)
    if result.returncode not in allowed:
        raise RuntimeError(f'Command failed (exit {result.returncode}): {command!r}\n{output}')
    return result
