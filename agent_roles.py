"""Specialized agents for the multi-agent design-to-code pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llm_client import MODEL
from tools import TOOLS, execute_tool
from ui import (
    print_action,
    print_banner,
    print_feedback,
    print_observation,
    print_raw_action,
)

DESIGN_PATH = "design_samples/design.json"
MAX_DESIGNER_STEPS = 3
MAX_CODER_STEPS = 6


class BaseAgent:
    """Shared LLM and tool-call plumbing for specialized agents."""

    name = "Agent"
    system_prompt = "你是一个 Agent。"
    allowed_tools: tuple[str, ...] = ()

    def __init__(self, client) -> None:
        self.client = client

    def _chat(self, messages: list[dict], tools: list[dict] | None = None):
        kwargs: dict[str, Any] = {"model": MODEL, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message

    def _tool_schemas(self, *names: str) -> list[dict]:
        return [tool for tool in TOOLS if tool["function"]["name"] in names]

    def _execute_call(self, call) -> str:
        name = call.function.name
        if name not in self.allowed_tools:
            return f"ERROR: {self.name} is not allowed to call {name}."
        try:
            arguments = json.loads(call.function.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
            return execute_tool(name, arguments)
        except (json.JSONDecodeError, ValueError) as exc:
            return f"ERROR: invalid tool arguments: {exc}"

    @staticmethod
    def _assistant_message(message) -> dict:
        return {
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
                for call in (message.tool_calls or [])
            ],
        }

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class DesignerAgent(BaseAgent):
    """Read and interpret the structured design when the request requires it."""

    name = "DesignerAgent"
    system_prompt = """你是设计理解 Agent。你不写代码，也不修改文件。
先根据本轮用户需求判断设计来源：
- 如果用户明确要求“按 design_samples/design.json 实现/检查”，必须调用 read_design；调用前不要假设设计内容。
- 如果用户提出具体的新需求（如冒泡排序、计算器），不要读取 design.json，直接根据用户需求生成设计摘要。
禁止把旧设计（例如 MotorController）套用到无关需求上。
摘要至少包含：目标、输入输出、边界条件、验收标准和可追溯 ID（如果用户或设计文件提供了 ID）。"""
    allowed_tools = ("read_design",)

    @staticmethod
    def _design_file_requested(requirement: str) -> bool:
        markers = (
            "design_samples", "design.json", "设计文件", "按设计",
            "根据设计", "现有设计", "读取设计",
        )
        return any(marker in requirement for marker in markers)

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        requirement = state.get("user_requirement", "(未提供)")
        print_banner(self.name, "设计理解：根据本轮需求选择设计来源")
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"本轮用户需求：\n{requirement}\n\n"
                    "如果明确要求按设计文件实现，请调用 read_design；"
                    "否则直接生成本轮需求对应的设计摘要。"
                ),
            },
        ]

        summary = ""
        read_design_used = False
        allow_design_tool = self._design_file_requested(requirement)
        tools = self._tool_schemas("read_design") if allow_design_tool else None
        for step in range(MAX_DESIGNER_STEPS):
            try:
                message = self._chat(messages, tools=tools)
            except Exception as exc:
                print_feedback(f"DesignerAgent LLM failed: {type(exc).__name__}: {exc}", "error")
                break
            if message.content:
                summary = message.content
            if not message.tool_calls:
                break

            messages.append(self._assistant_message(message))
            for call in message.tool_calls:
                raw = call.function.arguments or "{}"
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    print_action(call.function.name, parsed)
                else:
                    print_raw_action(call.function.name, raw)
                result = self._execute_call(call)
                print_observation(result, label="read_design")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                if not result.startswith("ERROR:"):
                    read_design_used = True

        if not summary:
            summary = f"根据用户需求生成设计摘要：{requirement}"
        source = "design.json" if read_design_used else "用户需求动态生成"
        state["design_content"] = (
            f"=== USER REQUIREMENT ===\n{requirement}\n\n"
            f"=== DESIGN SOURCE: {source} ===\n{summary}"
        )
        print(f"[{self.name}] 设计来源：{source}")
        print(f"[{self.name}] design_content 已更新（{len(state['design_content'])} chars）")
        return state


class PlannerAgent(BaseAgent):
    """Turn design understanding into an ordered development plan."""

    name = "PlannerAgent"
    system_prompt = """你是任务规划 Agent。你不写代码，也不修改文件。
严格只依据本轮 user_requirement 和 design_content 制定开发步骤：
1. 实现当前需求所需的功能；
2. 为当前需求编写 pytest 测试；
3. 运行测试并修复失败；
4. 如果设计摘要包含 Trace ID，再检查追溯注释。
禁止读取或假设 design.json 的内容；
禁止把旧设计（例如 MotorController）套用到无关需求上。
只输出严格的 JSON 字符串数组，不要输出解释、Markdown 或代码块。"""
    allowed_tools = ()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        print_banner(self.name, "任务规划：把设计转成开发步骤")
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"本轮用户需求：\n{state.get('user_requirement', '(未提供)')}\n\n"
                    f"设计理解如下，请输出开发步骤 JSON 数组：\n\n{state['design_content']}"
                ),
            },
        ]
        try:
            message = self._chat(messages)
            plan = self._parse_plan(message.content or "")
        except Exception as exc:
            print(f"[{self.name}] LLM plan failed: {type(exc).__name__}: {exc}")
            plan = []
        if not plan:
            plan = [
                "实现当前用户需求对应的业务代码",
                "为当前需求编写 pytest 测试",
                "运行 pytest，分析失败并修复",
                "如果设计摘要包含 Trace ID，检查追溯注释",
            ]
        state["plan"] = plan
        print(f"[{self.name}] 生成 {len(plan)} 个步骤：")
        for index, step in enumerate(plan, 1):
            print(f"  {index}. {step}")
        return state

    @staticmethod
    def _parse_plan(text: str) -> list[str]:
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        candidate = fenced.group(1).strip() if fenced else text.strip()
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            array = re.search(r"\[[\s\S]*\]", candidate)
            try:
                data = json.loads(array.group(0)) if array else None
            except json.JSONDecodeError:
                data = None
        if isinstance(data, dict):
            data = data.get("plan") or data.get("steps")
        if isinstance(data, list):
            return [item if isinstance(item, str) else json.dumps(item, ensure_ascii=False) for item in data][:12]
        lines = [re.sub(r"^\s*[-*\d.)]+\s*", "", line).strip() for line in text.splitlines()]
        return [line for line in lines if line and not line.startswith("```")][:12]


class CoderAgent(BaseAgent):
    """Write or repair implementation code and its tests."""

    name = "CoderAgent"
    system_prompt = """你是一个执行者。你不做需求分析，也不改变本轮设计目标。
根据本轮用户需求和设计摘要，使用 write_file 在 workspace/ 下写 Python 业务代码和 pytest 测试。
必须通过 write_file 真正写入文件，不能只在回复里展示代码。
注意：write_file 的 path 是相对于 workspace/ 的，不要写 workspace/ 前缀。
至少写入一个业务文件（例如 path='solution.py'）和一个测试文件（例如 path='tests/test_solution.py'）；
workspace/pytest.ini 的 testpaths=tests 只收集 tests/ 目录。
不要套用旧任务或旧设计；当前需求与 design.json 无关时，不要生成 MotorController。
如果提供了上一轮 test_result，先定位根因再修改；不得通过删除测试或放宽断言来刷绿。
只有在设计摘要明确提供 Trace ID 时，才添加 [Trace: ...] 注释，不要虚构。"""
    allowed_tools = ("write_file",)

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        phase = "修复代码" if state["iterations"] else "生成代码"
        print_banner(self.name, f"{phase}：iteration={state['iterations']}")
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"本轮用户需求：\n{state.get('user_requirement', '(未提供)')}\n\n"
                    f"设计理解：\n{state['design_content']}\n\n"
                    f"开发计划：\n{json.dumps(state['plan'], ensure_ascii=False, indent=2)}\n\n"
                    f"当前已写业务代码：\n{state['code_content'] or '(尚无)'}\n\n"
                    f"上一轮测试结果：\n{state['test_result'] or '(首次实现，无测试结果)'}\n\n"
                    "请通过 write_file 写入/覆盖实现和测试。"
                ),
            },
        ]
        written: list[tuple[str, str]] = []
        for step in range(MAX_CODER_STEPS):
            print(f"[{self.name}] ReAct step {step + 1}/{MAX_CODER_STEPS}")
            try:
                message = self._chat(messages, tools=self._tool_schemas("write_file"))
            except Exception as exc:
                print(f"[{self.name}] LLM call failed: {type(exc).__name__}: {exc}")
                break
            if message.content:
                print(f"Thought: {message.content}")
            if not message.tool_calls:
                break

            messages.append(self._assistant_message(message))
            for call in message.tool_calls:
                raw = call.function.arguments or "{}"
                try:
                    parsed_arguments = json.loads(raw)
                except json.JSONDecodeError:
                    parsed_arguments = None
                if isinstance(parsed_arguments, dict):
                    print_action(call.function.name, parsed_arguments)
                else:
                    print_raw_action(call.function.name, raw)
                result = self._execute_call(call)
                print_observation(result)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                if result.startswith("OK:"):
                    try:
                        arguments = json.loads(raw)
                        path = str(arguments.get("path", ""))
                        content = arguments.get("content", "")
                        if isinstance(content, str):
                            written.append((path, content))
                    except (json.JSONDecodeError, AttributeError):
                        pass

        implementations = [
            (path, content)
            for path, content in written
            if path.endswith(".py") and not Path(path).name.startswith("test_")
        ]
        if written:
            files_written = state.setdefault("files_written", [])
            for path, _ in written:
                if path and path not in files_written:
                    files_written.append(path)
        if implementations:
            state["code_content"] = implementations[-1][1]
            print(f"[{self.name}] code_content 已更新（{len(state['code_content'])} chars）")
        elif written:
            print_feedback("CoderAgent 只写入了测试或非业务文件，code_content 未更新。", "error")
        else:
            print_feedback("CoderAgent 未收到 write_file 调用，本轮没有生成业务代码。", "error")
        return state


class TesterAgent(BaseAgent):
    """Run the test suite and diagnose failures without editing code."""

    name = "TesterAgent"
    system_prompt = """你是一名严苛的测试员。你不修改代码。
你的职责是检查 pytest 结果是否真正验证了设计约束，并区分：
1. 业务实现错误；
2. 测试预期或测试覆盖错误；
3. 测试环境或路径问题。
输出失败根因、受影响的状态/约束 ID，以及给 Coder 的最小修复建议。
不要把失败的测试简单删除或放宽断言当成解决方案。"""
    allowed_tools = ("run_tests", "read_error")

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        print_banner(self.name, "质量验证：运行 pytest（有失败时再分析根因）")
        print_action("run_tests", {})
        output = execute_tool("run_tests", {})
        print_observation(output, label="pytest")
        if not state["code_content"].strip():
            state["test_result"] = (
                "TESTS_FAILED: CoderAgent did not produce implementation code.\n" + output
            )
            print_feedback("TesterAgent 未发现业务代码，验证失败。", "error")
            return state

        if output.startswith("TESTS_PASSED"):
            state["test_result"] = output
            return state

        print_action("read_error", {})
        error = execute_tool("read_error", {})
        detail = error if error.startswith("TESTS_FAILED") else output
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"本轮用户需求：\n{state.get('user_requirement', '(未提供)')}\n\n"
                    f"设计约束：\n{state['design_content']}\n\n"
                    f"pytest 输出：\n{detail}\n\n"
                    "请给出失败根因和最小修复建议，不要写代码。"
                ),
            },
        ]
        try:
            message = self._chat(messages)
            review = message.content or "(empty tester review)"
        except Exception as exc:
            review = f"LLM test review failed: {type(exc).__name__}: {exc}"

        state["test_result"] = f"{output}\n\n[TESTER REVIEW]\n{review}"
        return state
