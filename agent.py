"""Interactive single-agent CLI plus the multi-agent design-to-code orchestrator."""

import argparse
import json
import os
import sys
from pathlib import Path

from agent_roles import CoderAgent, DesignerAgent, PlannerAgent, TesterAgent
from llm_client import MODEL, create_client
from tools import TOOLS, execute_tool
from ui import (
    print_action,
    print_banner,
    print_feedback,
    print_observation,
    print_raw_action,
    print_round_end,
)

sys.stdout.reconfigure(encoding="utf-8")
MAX_STEPS = 10
MAX_ITERATIONS = 3
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

MULTI_MOCK_TRACE = [
    (
        "DesignerAgent",
        'read_design({"path": "design_samples/design.json"})',
        "design_content = REQ-MOTOR-001 + states/transitions/constraints",
    ),
    (
        "PlannerAgent",
        "LLM plan",
        "plan = [实现状态机, 编写安全约束测试, 运行 pytest, 检查 Trace]",
    ),
    (
        "CoderAgent",
        'write_file({"path": "motor_controller.py", ...})',
        "OK: wrote motor_controller.py",
    ),
    (
        "TesterAgent",
        "run_tests({})",
        "TESTS_FAILED (exit 1)\n2 failed, 29 passed",
    ),
    (
        "Orchestrator",
        "iterations += 1",
        "iterations = 1，携带 test_result 回到 CoderAgent",
    ),
    (
        "CoderAgent (repair)",
        'write_file({"path": "motor_controller.py", ...})',
        "OK: wrote motor_controller.py after test feedback",
    ),
    (
        "TesterAgent",
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
    print("[Mock] No API call; replaying a predefined single-agent run.\n")
    for step, (thought, action, observation) in enumerate(MOCK_TRACE, 1):
        print_banner(f"SingleAgent step {step}", thought)
        print(f"Action: {action}")
        print_observation(observation)
    print("Finish: 已生成 MotorController 和测试；31 个测试通过，覆盖 4 条转换与 5 条安全约束。")


def run_multi_mock() -> None:
    print("[Multi-Agent Mock] No API call; replaying Designer -> Planner -> Coder -> Tester.\n")
    for agent_name, action, observation in MULTI_MOCK_TRACE:
        if agent_name == "Orchestrator":
            print_feedback(observation, "warn")
        else:
            print_banner(agent_name, action)
            print_observation(observation)
    print("\nFinish: 多智能体协作完成；第 1 次修复后 31 个测试通过。")


def run_multi_pipeline(client, user_requirement: str) -> dict:
    """Run one fresh Designer -> Planner -> Coder -> Tester task."""
    state = {
        "user_requirement": user_requirement,
        "design_content": "",
        "plan": [],
        "code_content": "",
        "test_result": "",
        "iterations": 0,
    }
    designer = DesignerAgent(client)
    planner = PlannerAgent(client)
    coder = CoderAgent(client)
    tester = TesterAgent(client)

    print_banner("Orchestrator", "Designer -> Planner -> Coder -> Tester")

    state = designer.run(state)
    if state["design_content"].startswith("ERROR:"):
        print_feedback("设计读取失败，终止流水线。", "error")
        return state

    state = planner.run(state)

    while True:
        state = coder.run(state)
        state = tester.run(state)

        if state["test_result"].startswith("TESTS_PASSED"):
            print_feedback("质量门禁通过，流水线完成。", "success")
            break

        state["iterations"] += 1
        if state["iterations"] > MAX_ITERATIONS:
            print_feedback(
                f"TesterAgent 连续失败，iterations={state['iterations']} "
                f"超过上限 {MAX_ITERATIONS}，强制退出。",
                "error",
            )
            break
        print_feedback(
            f"TesterAgent 验证失败，进入第 {state['iterations']}/{MAX_ITERATIONS} 次修复；"
            "test_result 已回传给 CoderAgent。",
            "warn",
        )

    print_banner("Orchestrator", "Multi-Agent State")
    print(f"iterations: {state['iterations']}")
    print(f"plan_steps: {len(state['plan'])}")
    print(f"code_chars: {len(state['code_content'])}")
    status = state["test_result"].splitlines()[0] if state["test_result"] else "(no test result)"
    print(f"test_status: {status}")
    return state


def multi_agent_loop() -> None:
    """Interactive multi-agent CLI. Every task gets a fresh shared state."""
    load_dotenv()
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    print_banner("Orchestrator", "交互式多 Agent 模式")
    print("输入需求开始任务；输入 exit 或 quit 退出。每轮任务使用全新 State。")
    round_no = 0

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

        round_no += 1
        preview = user_input if len(user_input) <= 100 else user_input[:97] + "..."
        print_banner("Orchestrator", f"第 {round_no} 轮任务 | {preview}")
        run_multi_pipeline(client, user_input)
        print_round_end("本轮任务结束，等待新指令")


def agent_loop(client, messages: list[dict], turn: int) -> None:
    """Run one single-agent ReAct turn while keeping conversation history."""
    print_banner("InteractiveAgent", f"第 {turn} 轮对话")
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
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                result = f"ERROR: invalid JSON arguments: {exc}"
                print_raw_action(call.function.name, raw_arguments)
            else:
                if not isinstance(arguments, dict):
                    result = "ERROR: tool arguments must be a JSON object."
                    print_raw_action(call.function.name, raw_arguments)
                else:
                    print_action(call.function.name, arguments)
                    result = execute_tool(call.function.name, arguments)
            print_observation(result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    print(f"\n[Stop] Reached MAX_STEPS={MAX_STEPS}; no final answer was produced.")


def interactive_mode() -> None:
    """Start a persistent multi-turn single-agent CLI."""
    load_dotenv()
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print_banner("InteractiveAgent", "启动交互式会话")
    print("输入 exit 或 quit 退出。")
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
    parser = argparse.ArgumentParser(description="Interactive and multi-agent design-to-code system")
    parser.add_argument("--mock", action="store_true", help="replay a fixed trace without API access")
    parser.add_argument("--multi", action="store_true", help="start interactive multi-agent mode")
    args = parser.parse_args()

    if args.mock:
        run_multi_mock() if args.multi else run_mock()
    elif args.multi:
        multi_agent_loop()
    else:
        interactive_mode()
