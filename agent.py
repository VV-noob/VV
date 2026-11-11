"""Interactive single-agent CLI plus the multi-agent design-to-code orchestrator."""

import argparse
import json
import os
import re
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

ROUTER_PROMPT = """你是多 Agent 系统的意图路由器。请根据最近对话、当前输入和最近 State 判断用户意图。
只输出一个 JSON 对象，不要输出 Markdown 或其他文字：
{"intent":"code","user_requirement":"具体代码任务","reason":"一句话理由"}
{"intent":"query","user_requirement":"","reason":"一句话理由"}
{"intent":"chat","user_requirement":"","reason":"一句话理由"}

三类意图：
- CODE：要求编写、修改、修复、重构、运行或测试代码，需要产生或修改文件。
- QUERY：询问任务状态、上一轮结果、代码位置、文件路径、失败原因、概念解释、实现说明。
- CHAT：问候、感谢、寒暄、与任务无关的闲聊。

关键规则：
- “你刚刚做了什么”“代码在哪里”“为什么失败”“解释一下”都是 QUERY，不是 CODE。
- 即使 QUERY 句子里出现“写”“代码”“测试”等词，也不能进入 CODE 流水线。
- CODE 的 user_requirement 要提取本轮真正要实现的代码目标；QUERY/CHAT 留空。
- 必须结合历史理解“刚才”“继续”“它”等指代。"""

DIRECT_PROMPT = """你是多 Agent 编程助手。你只根据最近对话和最近一次代码任务状态直接回答。
不要调用工具，不要读取或修改文件，不要重新运行 Designer/Coder/Tester 流水线。
如果用户询问代码在哪里，优先回答最近 State 中记录的文件路径；
如果最近没有代码任务，明确说明还没有执行过代码生成。
如果用户问“你刚刚完成了什么”，依据任务状态和测试结果回答。
回答要简洁、自然。"""

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


def _parse_json_object(text: str) -> dict | None:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", candidate)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _fallback_route(user_input: str) -> dict:
    query_words = (
        "刚刚", "刚才", "哪里", "在哪", "做了什么", "干了什么", "写了什么",
        "完成了什么", "为什么", "怎么", "如何", "解释", "说明", "总结",
        "汇报", "状态", "结果", "成功了吗", "失败", "文件路径", "代码位置",
        "有哪些文件", "吗", "？", "?",
    )
    if any(word in user_input for word in query_words):
        return {"intent": "query", "user_requirement": "", "reason": "关键词回退"}
    code_words = (
        "写", "实现", "修改", "修复", "重构", "运行", "测试", "代码",
        "文件", "改成", "换成", "调整", "增加", "删除", "更新", "补",
    )
    if any(word in user_input for word in code_words):
        return {"intent": "code", "user_requirement": user_input, "reason": "关键词回退"}
    return {"intent": "chat", "user_requirement": "", "reason": "关键词回退"}


def _looks_like_query(user_input: str) -> bool:
    markers = (
        "在哪里", "在哪", "代码位置", "文件路径", "保存到哪", "写到哪里",
        "做了什么", "干了什么", "完成了什么", "写了什么", "哪些文件",
        "测试结果如何", "成功了吗",
    )
    return any(marker in user_input for marker in markers)


def route_intent(client, user_input: str, history: list[dict]) -> dict:
    messages = [{"role": "system", "content": ROUTER_PROMPT}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_input})
    try:
        response = client.chat.completions.create(model=MODEL, messages=messages)
        data = _parse_json_object(response.choices[0].message.content or "")
    except Exception as exc:
        print_feedback(f"Intent router failed: {type(exc).__name__}: {exc}", "error")
        data = None
    intents = {"code", "query", "chat"}
    if not data or str(data.get("intent", "")).strip().lower() not in intents:
        return _fallback_route(user_input)
    intent = str(data["intent"]).strip().lower()
    requirement = str(data.get("user_requirement", "")).strip()
    # Guard against a model that mislabels an explicit location/status question as CODE.
    if intent == "code" and _looks_like_query(user_input):
        intent, requirement = "query", ""
    if intent == "code" and not requirement:
        requirement = user_input
    return {
        "intent": intent,
        "user_requirement": requirement,
        "reason": str(data.get("reason", "")).strip() or "LLM route",
    }


def state_context(state: dict | None) -> str:
    if not state:
        return "最近没有执行过代码任务。"
    status = state["test_result"].splitlines()[0] if state["test_result"] else "(no test result)"
    files = state.get("files_written") or []
    return (
        f"最近一次代码任务：{state.get('user_requirement', '(unknown)')}\n"
        f"测试状态：{status}\n"
        f"修复次数：{state.get('iterations', 0)}\n"
        f"写入文件：{', '.join(files) if files else '(未记录)'}"
    )


def answer_direct(client, user_input: str, history: list[dict], state: dict | None) -> str:
    system = f"{DIRECT_PROMPT}\n\n{state_context(state)}"
    messages = [{"role": "system", "content": system}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_input})
    try:
        response = client.chat.completions.create(model=MODEL, messages=messages)
        return response.choices[0].message.content or "(empty response)"
    except Exception as exc:
        return f"ERROR: direct answer failed: {type(exc).__name__}: {exc}"


def remember(history: list[dict], role: str, content: str) -> None:
    history.append({"role": role, "content": content})
    del history[:-12]


def summarize_state(state: dict) -> str:
    status = state["test_result"].splitlines()[0] if state["test_result"] else "(no test result)"
    plan = "; ".join(state["plan"][:5]) or "(no plan)"
    files = state.get("files_written") or []
    return (
        f"本轮代码任务需求：{state['user_requirement']}。"
        f"测试状态：{status}。修复次数：{state['iterations']}。"
        f"写入文件：{', '.join(files) if files else '(未记录)'}。"
        f"计划：{plan}。"
    )


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
        "files_written": [],
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
    """Interactive multi-agent CLI with intent routing and per-task state."""
    load_dotenv()
    try:
        client = create_client()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return

    print_banner("Orchestrator", "交互式多 Agent 模式")
    print("输入需求开始；QUERY/CHAT 会直接回答；CODE 任务才进入多 Agent 流水线。")
    print("输入 exit 或 quit 退出。")
    history: list[dict] = []
    last_state: dict | None = None
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
        print_banner("Orchestrator", f"第 {round_no} 轮输入 | {preview}")

        route = route_intent(client, user_input, history)
        intent = route["intent"]
        reason = route["reason"]
        print_banner("Orchestrator", f"路由意图：{intent.upper()} | {reason[:120]}")

        if intent in {"query", "chat"}:
            answer = answer_direct(client, user_input, history, last_state)
            print_banner("DirectAnswer", f"{intent.upper()} | 直接回答（不进入代码流水线）")
            print(answer)
            remember(history, "user", user_input)
            remember(history, "assistant", answer)
            ending = "本轮查询结束，等待新指令" if intent == "query" else "本轮对话结束，等待新指令"
            print_round_end(ending)
            continue

        requirement = route["user_requirement"] or user_input
        print_feedback(f"代码任务已识别，进入多 Agent 流水线：{requirement[:160]}", "warn")
        state = run_multi_pipeline(client, requirement)
        last_state = state
        summary = summarize_state(state)
        remember(history, "user", user_input)
        remember(history, "assistant", summary)
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
