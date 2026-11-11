"""Terminal presentation helpers for the multi-agent pipeline."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
if COLOR and os.name == "nt":
    os.system("")  # Enable ANSI escape sequences in Windows terminals.

RESET = "\033[0m" if COLOR else ""
BOLD = "\033[1m" if COLOR else ""
DIM = "\033[2m" if COLOR else ""
RED = "\033[31m" if COLOR else ""
GREEN = "\033[32m" if COLOR else ""
YELLOW = "\033[33m" if COLOR else ""
BLUE = "\033[34m" if COLOR else ""
MAGENTA = "\033[35m" if COLOR else ""
CYAN = "\033[36m" if COLOR else ""
WHITE = "\033[37m" if COLOR else ""
SEPARATOR = "=" * 72


def _agent_color(name: str) -> str:
    colors = {
        "Designer": BLUE,
        "Planner": MAGENTA,
        "Coder": CYAN,
        "Tester": YELLOW,
        "Orchestrator": GREEN,
    }
    for prefix, color in colors.items():
        if name.startswith(prefix):
            return color
    return WHITE


def print_banner(agent_name: str, action: str) -> None:
    """Print a clearly separated, agent-colored section header."""
    color = _agent_color(agent_name)
    print(f"\n{color}{BOLD}{SEPARATOR}")
    print(f" {agent_name} | {action}")
    print(f"{SEPARATOR}{RESET}")


def format_action(name: str, arguments: dict[str, Any]) -> str:
    """Format a tool call without dumping large file contents."""
    if name == "write_file":
        path = Path(str(arguments.get("path", "?"))).name
        content = arguments.get("content", "")
        size = len(content) if isinstance(content, str) else 0
        return f"write_file(path={path!r}, content='[省略 {size} 字]')"

    payload = json.dumps(arguments, ensure_ascii=False)
    if len(payload) > 180:
        payload = payload[:177] + "..."
    return f"{name}({payload})"


def print_action(name: str, arguments: dict[str, Any]) -> None:
    print(f"{DIM}Action: {format_action(name, arguments)}{RESET}")


def print_raw_action(name: str, raw: str) -> None:
    preview = raw if len(raw) <= 180 else raw[:177] + "..."
    print(f"{DIM}Action: {name}({preview}){RESET}")


def format_observation(text: str, max_lines: int = 15) -> str:
    """Keep the beginning and end of long tool output."""
    if not isinstance(text, str):
        text = str(text)
    lines = text.splitlines() or [""]
    if len(lines) > max_lines:
        head = max_lines // 2
        tail = max_lines - head
        omitted = len(lines) - head - tail
        lines = lines[:head] + [f"... (省略 {omitted} 行) ..."] + lines[-tail:]
    clipped = []
    for line in lines:
        clipped.append(line if len(line) <= 240 else line[:237] + "...")
    return "\n".join(clipped)


def print_observation(text: str, label: str = "Observation") -> None:
    if not isinstance(text, str):
        text = str(text)
    if text.startswith("TESTS_FAILED"):
        color = RED
    elif text.startswith("TESTS_PASSED"):
        color = GREEN
    else:
        color = DIM
    print(f"{color}{label}: {format_observation(text)}{RESET}")


def print_feedback(message: str, level: str = "warn") -> None:
    """Highlight an orchestration event such as a repair iteration."""
    if level == "error":
        color, label = RED, "ERROR"
    elif level == "success":
        color, label = GREEN, "PASS"
    else:
        color, label = YELLOW, "ITERATION"
    print(f"\n{color}{BOLD}{SEPARATOR}")
    print(f" [{label}] {message}")
    print(f"{SEPARATOR}{RESET}")


def print_round_end(message: str = "本轮任务结束，等待新指令") -> None:
    """Mark the end of one interactive multi-agent task."""
    print(f"\n{CYAN}{BOLD}{SEPARATOR}")
    print(f"========== {message} ==========")
    print(f"{SEPARATOR}{RESET}")

