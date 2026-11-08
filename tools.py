"""Sandboxed tools exposed to the coding agent."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
DESIGN_DIR = (ROOT / "design_samples").resolve()
WORKSPACE = (ROOT / "workspace").resolve()
_last_test_output, _last_test_failed = "No tests have been run yet.", False


def _inside(path: Path, directory: Path) -> bool:
    return str(path) == str(directory) or str(path).startswith(str(directory) + os.sep)


def _read_design(args: dict[str, Any]) -> str:
    raw = Path(str(args["path"]))
    candidate = (raw if raw.is_absolute() else ROOT / raw).resolve()
    if candidate.parent != DESIGN_DIR:
        candidate = (DESIGN_DIR / raw).resolve()
    if candidate.parent != DESIGN_DIR:
        return "ERROR: read_design path must stay inside design_samples/."
    if not candidate.is_file():
        return f"ERROR: design file not found: {raw}"
    return candidate.read_text(encoding="utf-8")


def _write_file(args: dict[str, Any]) -> str:
    raw, content = Path(str(args["path"])), args["content"]
    if not isinstance(content, str):
        return "ERROR: content must be a string."
    target = (raw if raw.is_absolute() else WORKSPACE / raw).resolve()
    if target == WORKSPACE or not _inside(target, WORKSPACE):
        return "ERROR: write_file path must stay inside workspace/."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: wrote {target.relative_to(WORKSPACE).as_posix()} ({len(content)} chars)"


def _run_tests(_: dict[str, Any]) -> str:
    global _last_test_output, _last_test_failed
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"], cwd=WORKSPACE, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        output = output or f"pytest produced no output (exit {proc.returncode})."
        _last_test_failed = proc.returncode != 0
        _last_test_output = f"{'TESTS_FAILED' if _last_test_failed else 'TESTS_PASSED'} (exit {proc.returncode})\n{output}"
    except subprocess.TimeoutExpired:
        _last_test_failed = True
        _last_test_output = "TESTS_FAILED (timeout)\nERROR: pytest timed out after 30 seconds."
    except Exception as exc:
        _last_test_failed = True
        _last_test_output = f"TESTS_FAILED (runner error)\nERROR: could not run pytest: {type(exc).__name__}: {exc}"
    return _last_test_output


def _read_error(_: dict[str, Any]) -> str:
    if not _last_test_failed:
        return "No failing tests: the last test run passed or tests have not run yet."
    return _last_test_output


def execute_tool(name: str, args: dict[str, Any]) -> str:
    handlers: dict[str, Callable[[dict[str, Any]], str]] = {
        "read_design": _read_design,
        "write_file": _write_file,
        "run_tests": _run_tests,
        "read_error": _read_error,
    }
    handler = handlers.get(name)
    if handler is None:
        return f"ERROR: unknown tool: {name}"
    try:
        return handler(args)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Emit a complete OpenAI function schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    _tool("read_design", "Read a design JSON file from design_samples/.",
          {"path": {"type": "string", "description": "Path, e.g. design_samples/design.json."}}, ["path"]),
    _tool("write_file", "Write UTF-8 text under workspace/, creating parent directories.",
          {"path": {"type": "string", "description": "Relative path under workspace/, e.g. greeting.py."},
           "content": {"type": "string", "description": "Complete file content to write."}},
          ["path", "content"]),
    _tool("run_tests", "Run all generated pytest tests in workspace/; return pass/fail status, stdout and stderr (30s timeout).", {}, []),
    _tool("read_error", "Return the most recent failing pytest output; use it to distinguish implementation bugs from wrong test expectations.", {}, []),
]
