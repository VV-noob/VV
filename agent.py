"""Interactive ReAct coding agent: read a design, write code, test, repair."""

import argparse
import json
import os
import sys
from pathlib import Path

from llm_client import MODEL, create_client
from tools import TOOLS, execute_tool

sys.stdout.reconfigure(encoding="utf-8")
MAX_STEPS = 10
SYSTEM_PROMPT = """你是一个交互式编程 Agent。你可以使用工具读取设计、写代码、跑测试。
当用户提出需求或修改意见时，请自主决定是否需要调用工具。如果测试失败，请分析错误并修复。如果任务完成，请简短汇报。不要重复相同的失败调用。"""

MOCK_TRACE = [
    (
        "读取工业设计，提取状态机、约束和追溯 ID。",
        'read_design({"path": "design_samples/design.json"})',
        '{"requirement_id": "REQ-MOTOR-001", "class": "MotorController", "states": ["IDLE", "RUNNING", "FAULT"], "transitions": 4, "constraints": 5}',
    ),
    (
        "用 Class 实现状态机，并把转换和约束绑定到追溯注释。",
        'write_file({"path": "motor_controller.py", "content": "<MotorController + # [Trace: REQ-MOTOR-001/...]>"})',
        "OK: wrote motor_controller.py (5115 chars)",
    ),
    (
        "生成覆盖初始状态、合法转换和安全约束的测试。",
        'write_file({"path": "test_motor_controller.py", "content": "<31 pytest cases for AC-001..AC-008>"})',
        "OK: wrote test_motor_controller.py (8826 chars)",
    ),
    (
        "运行完整测试套件并确认安全约束。",
        "run_tests({})",
        "TESTS_PASSED (exit 0)\n31 passed in 0.04s",
    ),
]


def load_dotenv() -> None:
    """Load DEEPSEEK_API_KEY from .env without overriding the shell environment."""
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def run_mock() -> None:
    print("[Mock] No API call; replaying a predefined successful run.\n")
    for step, (thought, action, observation) in enumerate(MOCK_TRACE, 1):
        print(f"[Step {step}] Thought: {thought}")
        print(f"Action: {action}")
        print(f"Observation: {observation}\n")
    print("Finish: 已生成 MotorController 和测试；31 个测试通过，覆盖 4 条转换与 5 条安全约束。")


def agent_loop(client, messages: list[dict], turn: int) -> None:
    """Run one ReAct turn while keeping the shared conversation history."""
    print(f"\n========== 第 {turn} 轮对话 ==========")
    for step in range(MAX_STEPS):
        try:
            response = client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
            )
        except Exception as exc:
            print(f"[Stop] LLM request failed: {type(exc).__name__}: {exc}")
            return

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        print(f"\n[Step {step + 1}]")
        if message.content:
            print(f"Thought: {message.content}")

        if not tool_calls:
            final_content = message.content or "(empty response)"
            print(f"Finish: {final_content}")
            messages.append({"role": "assistant", "content": final_content})
            return

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ],
        })

        for call in tool_calls:
            raw_arguments = call.function.arguments or "{}"
            print(f"Action: {call.function.name}({raw_arguments})")
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                result = f"ERROR: invalid JSON arguments: {exc}"
            else:
                if not isinstance(arguments, dict):
                    result = "ERROR: tool arguments must be a JSON object."
                else:
                    result = execute_tool(call.function.name, arguments)
            print(f"Observation: {result}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    print(f"\n[Stop] Reached MAX_STEPS={MAX_STEPS}; no final answer was produced.")


def interactive_mode() -> None:
    """Start a persistent multi-turn CLI while preserving conversation context."""
    load_dotenv()
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("交互式 Coding Agent 已启动。输入 exit 或 quit 退出。")
    turn = 0

    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("已退出。")
            break

        turn += 1
        messages.append({"role": "user", "content": user_input})
        agent_loop(client, messages, turn)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interactive design-to-code ReAct agent")
    parser.add_argument("--mock", action="store_true", help="replay a fixed trace without API access")
    args = parser.parse_args()
    run_mock() if args.mock else interactive_mode()
