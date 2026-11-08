"""Minimal ReAct coding agent: read a design, write code, test, repair."""

import argparse
import json
import sys

from llm_client import MODEL, create_client
from tools import TOOLS, execute_tool

sys.stdout.reconfigure(encoding="utf-8")
MAX_STEPS = 10
SYSTEM_PROMPT = """你是一个编程 Agent，目标是根据 design.json 生成代码并通过 pytest 测试。
必须按顺序工作：先调用 read_design 读取设计；再调用 write_file 写入 workspace/；
然后调用 run_tests 验证。如果测试失败，调用 read_error 查看错误，再修改代码并重测。
只使用提供的工具；不要重复完全相同的失败调用；最多执行 10 步。
测试通过后不要再调用工具，直接输出简短最终答复。"""

MOCK_TRACE = [
    (
        "先读取设计规格，确认模块名、函数签名和输出格式。",
        'read_design({"path": "design_samples/design.json"})',
        '{"module": "greeting", "function": {"name": "greet", "description": "Return exactly '
        "'Hello, <name>!' for the given name.\", \"input\": [{\"name\": \"name\", \"type\": \"string\"}], \"output\": \"string\"}}",
    ),
    (
        "设计要求 greeting.greet(name) 返回 Hello, <name>!，写入实现。",
        'write_file({"path": "greeting.py", "content": "def greet(name: str) -> str:\\n'
        '    return f\\"Hello, {name}!\\"\\n"})',
        "OK: wrote greeting.py (58 chars)",
    ),
    (
        "实现已写入，运行 pytest 验证行为。",
        "run_tests({})",
        "..                                                                       [100%]\n"
        "2 passed in 0.01s\n[exit code: 0]",
    ),
]


def run_mock() -> None:
    print("[Mock] No API call; replaying a predefined successful run.\n")
    for step, (thought, action, observation) in enumerate(MOCK_TRACE, 1):
        print(f"[Step {step}] Thought: {thought}")
        print(f"Action: {action}")
        print(f"Observation: {observation}\n")
    print("Finish: 已根据设计实现 greet，2 个 pytest 测试全部通过。")


def run_real() -> None:
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "设计文件是 design_samples/design.json，测试在 workspace/。请开始实现并验证。"},
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
