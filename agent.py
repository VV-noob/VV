"""Minimal ReAct coding agent: read a design, write code, test, repair."""

import argparse
import json
import sys

from llm_client import MODEL, create_client
from tools import TOOLS, execute_tool

sys.stdout.reconfigure(encoding="utf-8")
MAX_STEPS = 10
SYSTEM_PROMPT = """你是工业级 Python 编程 Agent，目标是把 design.json 实现为可验证的类状态机。
1. 必须先调用 read_design，提取 requirement_id、states、transitions、constraints、接口、异常和验收标准。
2. 编写业务代码：必须用 Class 实现显式状态机；类名、方法、异常严格遵循设计；每个状态、转换和约束处写 `# [Trace: <requirement_id>/<ID>]` 追溯注释。
3. 必须在 workspace/ 生成当前设计的 pytest 测试，覆盖初始状态、每条合法转换和每条约束/异常路径；若存在上一轮遗留测试，用 write_file 覆盖为当前测试，禁止依赖旧测试通过。
4. 运行 run_tests。失败时先 read_error，根据断言和堆栈判断是业务实现错误还是测试预期错误；修复根因，必要时重构，禁止删除测试、放宽断言或削弱安全约束。
5. 只有测试全部通过才能 Finish；最终答复汇总生成文件、测试数和追溯覆盖。最多 10 步，不要重复完全相同的失败调用。
"""

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


def run_mock() -> None:
    print("[Mock] No API call; replaying a predefined successful run.\n")
    for step, (thought, action, observation) in enumerate(MOCK_TRACE, 1):
        print(f"[Step {step}] Thought: {thought}")
        print(f"Action: {action}")
        print(f"Observation: {observation}\n")
    print("Finish: 已生成 MotorController 和测试；31 个测试通过，覆盖 4 条转换与 5 条安全约束。")


def run_real() -> None:
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "设计文件是 design_samples/design.json。workspace/ 中已有上一轮参考实现和测试；请以当前设计为准重新生成并验证，必要时覆盖参考文件，确保 pytest 只验证 REQ-MOTOR-001。"},
    ]

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
            print(f"Finish: {message.content or '(empty response)'}")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minimal design-to-code ReAct agent")
    parser.add_argument("--mock", action="store_true", help="replay a fixed trace without API access")
    args = parser.parse_args()
    run_mock() if args.mock else run_real()
