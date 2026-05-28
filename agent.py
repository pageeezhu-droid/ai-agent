"""
Agent 核心模块 —— ReAct 循环：思考 → 行动 → 观察
"""

import json
import os
import re
from datetime import datetime

from tools import call_tool, get_tool_descriptions, WORKSPACE_DIR
from llm_api import call_llm, call_llm_stream


SYSTEM_PROMPT = """你是一个 AI 智能助手，你可以调用工具来解决用户的问题，而不是凭你自己的知识回答。

当前时间：{current_date}
你的训练数据有截止日期，涉及"今天""现在"等时间问题时以这个时间为准。

---

## 可用工具

{tool_descriptions}

---

## 工作方式（CoT 思考链）

严格按以下步骤，每次只能调用一个工具：

1. **思考**：用一行文字分析当前状态，说明接下来要做什么、为什么
2. **行动**：输出 JSON 指令（必须用 ```json 代码块包裹）
3. **观察**：等待工具返回结果
4. **循环**：根据结果决定下一步或给出最终答案

---

## 输出格式

调用工具时，**必须先输出「思考：...」行，再输出 JSON 代码块**：

思考：需要先搜索获取相关数据
```json
{{"action": "工具名", "args": {{"参数名": "参数值"}}}}
```

最终回答时，给出 final_answer（不需要思考行）：

```json
{{"action": "final_answer", "content": "你的完整回答"}}
```

---

## 禁止规则

严格禁止以下行为：

- calculate 工具**只能做纯数学运算**（加减乘除、幂、绝对值等），**禁止**传入 Python 代码、import 语句、exec/eval/__builtins__
- read_file 参数必须是具体文件名，**禁止**传入 "." "/" 等路径（查看目录请用 list_files）
- write_file 写入代码时，content 中的双引号必须转义为 \\"，换行必须用 \\n，反斜杠必须用 \\\\
- run_python 的 code 参数**不能为空**，耗时操作注意 10 秒超时限制
- **禁止**凭空编造数据，必须基于工具返回的真实结果回答
- 工具调用失败后**必须反思原因**，换一种方式重试，**禁止**用完全相同的参数

---

## 示例对话

**示例 1 — 使用计算器：**

用户：爱因斯坦 1879 年出生，1955 年去世，活了多少岁？

思考：需要用 calculate 计算 1955 - 1879
```json
{{"action": "calculate", "args": {{"expression": "1955-1879"}}}}
```
工具返回：76
思考：计算完成，1955-1879=76
```json
{{"action": "final_answer", "content": "爱因斯坦活了 76 岁（1955 - 1879 = 76）。"}}
```

**示例 2 — 搜索并保存文件：**

用户：搜索量子计算最新进展，保存到 quantum.txt

思考：先搜索互联网获取量子计算的最新信息
```json
{{"action": "search_web", "args": {{"query": "量子计算 最新进展"}}}}
```
工具返回：量子计算在2026年取得多项突破...
思考：搜索结果已获取，现在写入 quantum.txt，注意 JSON 转义
```json
{{"action": "write_file", "args": {{"filename": "quantum.txt", "content": "量子计算最新进展\\n\\n量子计算在2026年取得多项突破..."}}}}
```
工具返回：已成功写入文件「quantum.txt」
思考：搜索和保存都已完成
```json
{{"action": "final_answer", "content": "已搜索量子计算的最新进展，并保存到 quantum.txt 文件中。"}}
```

**示例 3 — 执行 Python 代码：**

用户：打印 1 到 100 的质数，保存到 primes.txt

思考：用 run_python 计算质数，结果写入文件
```json
{{"action": "run_python", "args": {{"code": "def is_prime(n):\\n    if n < 2: return False\\n    for i in range(2, int(n**0.5)+1):\\n        if n % i == 0: return False\\n    return True\\nprimes = [str(n) for n in range(1, 101) if is_prime(n)]\\nprint(','.join(primes))"}}}}
```
工具返回：2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97
思考：已获得质数列表，写入 primes.txt
```json
{{"action": "write_file", "args": {{"filename": "primes.txt", "content": "2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97"}}}}
```
工具返回：已成功写入文件「primes.txt」
思考：质数已计算并保存
```json
{{"action": "final_answer", "content": "1 到 100 的质数共 25 个：2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97。已保存到 primes.txt。"}}
```

**示例 4 — 工具失败反思重试：**

用户：看看 result.txt 里面写了什么

思考：先读取 result.txt 文件内容
```json
{{"action": "read_file", "args": {{"filename": "result.txt"}}}}
```
工具返回：文件「result.txt」不存在
反思：read_file 失败，文件不存在。先用 list_files 查看目录下有哪些文件，再用正确文件名读取。
思考：文件不存在，先用 list_files 查看目录内容
```json
{{"action": "list_files", "args": {{"path": ""}}}}
```
工具返回：[FILE] data.txt\n[FILE] output.txt
思考：目录中没有 result.txt，只有 data.txt 和 output.txt，告知用户
```json
{{"action": "final_answer", "content": "抱歉，目录下没有 result.txt。当前文件有：data.txt、output.txt。你想查看哪个？"}}
```

---

## 重要规则

- 每次只能调用一个工具，等结果返回后再决定下一步
- 基于工具返回的真实结果进行推理，不要猜测
- 最终回答用中文，引用使用过的数据来源
- 工具执行结果用「工具返回：」前缀返回给你
- **写入任何包含代码或特殊字符的文件时，务必正确转义 JSON**：双引号 → \\"，换行 → \\n，反斜杠 → \\\\"""


# ── JSON 解析 ─────────────────────────────────────────────

def parse_action(text: str) -> dict | None:
    """从 LLM 回复中提取 action JSON，失败返回 None"""
    # 1) 匹配 ```json ... ``` 代码块
    for match in re.findall(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        json_str = _extract_json(match)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    # 2) 尝试直接解析整段文本
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 3) 暴力提取第一个 { ... }（括号计数法处理嵌套）
    json_str = _extract_json(text)
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    return None


def _extract_json(text: str) -> str | None:
    """括号计数法：正确处理嵌套花括号"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ── 上下文管理 ───────────────────────────────────────────

MAX_MESSAGES = 20  # 发给 LLM 的消息上限


def trim_messages(messages: list) -> list:
    """超出 MAX_MESSAGES 时丢弃最早的对话"""
    excess = len(messages) - MAX_MESSAGES
    return messages[excess:] if excess > 0 else messages


# ── 自反思：错误检测 + 经验库 ──────────────────────────────

_ERROR_KEYWORDS = ["错误", "出错", "失败", "超时", "不存在", "未找到", "状态码", "没有权限"]
_EXPERIENCE_FILE = os.path.join(WORKSPACE_DIR, "experience.json")


def _is_tool_error(result: str) -> bool:
    """检测工具返回是否为错误"""
    for kw in _ERROR_KEYWORDS:
        if kw in result:
            return True
    return False


def _save_experience(tool: str, args: dict, error: str) -> None:
    """将失败经验持久化到 workspace/experience.json"""
    entry = {
        "tool": tool,
        "args": args,
        "error": error[:200],
        "timestamp": datetime.now().isoformat(),
    }
    try:
        data = []
        if os.path.exists(_EXPERIENCE_FILE):
            with open(_EXPERIENCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append(entry)
        if len(data) > 20:
            data = data[-20:]
        with open(_EXPERIENCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_experience_text() -> str:
    """加载经验库摘要，注入系统提示词"""
    try:
        if not os.path.exists(_EXPERIENCE_FILE):
            return ""
        with open(_EXPERIENCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return ""
        recent = data[-3:]
        lines = ["\n## 经验库（从过往错误中学习，避免重复失败）"]
        for e in recent:
            lines.append(f"- {e['tool']} 曾经失败：{e['error'][:120]}")
        return "\n".join(lines)
    except Exception:
        return ""


# ── 长期记忆：摘要压缩 + 持久化 ────────────────────────────

_MEMORY_FILE = os.path.join(WORKSPACE_DIR, "memory.json")
_MEMORY_TRIGGER = 16   # 对话超过此条数触发摘要
_MEMORY_KEEP = 6       # 保留最近条数

_SUMMARY_PROMPT = """从以下对话中提取关键信息作为长期记忆。只保留对未来有帮助的内容：
- 用户个人信息（姓名、身份、偏好）
- 重要上下文和未完成任务
- 用户的长期目标或兴趣

忽略已完成的一次性操作、工具调用细节、闲聊。

对话：
{text}

摘要（不超过 200 字，中文）："""


def _summarize_conversation(messages: list) -> str:
    """调用 LLM 将对话压缩为摘要"""
    if not messages:
        return ""
    text = "\n".join([
        f"{m['role']}: {str(m['content'])[:300]}" for m in messages[:10]
    ])
    result = call_llm(
        [{"role": "user", "content": text}],
        system_prompt=_SUMMARY_PROMPT,
        temperature=0.1,
    )
    return result.strip()


def _load_memory() -> str:
    """从 workspace/memory.json 加载持久记忆"""
    try:
        if not os.path.exists(_MEMORY_FILE):
            return ""
        with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return "\n".join([f"- {m}" for m in data[-5:]])
        return ""
    except Exception:
        return ""


def _save_memory(summary: str) -> None:
    """追加摘要到 workspace/memory.json"""
    if not summary or summary.isspace():
        return
    try:
        data = []
        if os.path.exists(_MEMORY_FILE):
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append(summary.strip())
        if len(data) > 20:
            data = data[-20:]
        with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def manage_memory(conv_history: list) -> tuple[list, str | None]:
    """如果对话超过阈值，摘要最旧部分并返回新历史和摘要"""
    if len(conv_history) <= _MEMORY_TRIGGER:
        return conv_history, None
    oldest = conv_history[:len(conv_history) - _MEMORY_KEEP]
    summary = _summarize_conversation(oldest)
    _save_memory(summary)
    return conv_history[-_MEMORY_KEEP:], summary


# ── Agent 主循环 ──────────────────────────────────────────

WEEKDAY_MAP = {str(i): w for i, w in enumerate(
    ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
)}


def build_system_prompt() -> str:
    """注入当前时间和工具列表"""
    now = datetime.now()
    weekday = WEEKDAY_MAP[now.strftime("%w")]
    current_date = now.strftime(f"%Y年%m月%d日 %H:%M，{weekday}")
    prompt = SYSTEM_PROMPT.format(
        current_date=current_date,
        tool_descriptions=get_tool_descriptions(),
    ) + _load_experience_text()
    memory = _load_memory()
    if memory:
        prompt += f"\n\n## 长期记忆\n以下是此前对话中提取的关键信息：\n{memory}\n\n当用户提及时，优先参考这些信息。"
    return prompt


def _prepare_messages(user_input: str, conversation_history: list | None) -> list:
    """将用户输入与短期记忆组装为消息列表"""
    if conversation_history:
        return list(conversation_history) + [{"role": "user", "content": user_input}]
    return [{"role": "user", "content": user_input}]


def run_agent(user_input: str, max_rounds: int = 8,
              conversation_history: list | None = None) -> list:
    """非流式 Agent，返回完整对话记录（终端调试用）"""
    system_prompt = build_system_prompt()
    messages = _prepare_messages(user_input, conversation_history)
    full_history = [{"role": "system", "content": system_prompt}]

    for round_num in range(max_rounds):
        print(f"\n{'='*50}\n[{round_num + 1}]\n{'='*50}")

        response = call_llm(messages, system_prompt=system_prompt)
        print(f"[LLM] {response[:200]}\n")

        messages.append({"role": "assistant", "content": response})
        full_history.append({"role": "assistant", "content": response})

        action = parse_action(response)
        if action is None:
            print(f"[Agent] {response[:200]}")
            return full_history

        action_name = action.get("action", "")
        action_args = action.get("args", {})

        if action_name == "final_answer":
            content = action.get("content", "")
            print(f"[Agent] {content}")
            full_history.append({"role": "assistant", "content": content})
            return full_history

        print(f"[工具] {action_name}({action_args})")
        result = call_tool(action_name, action_args)
        print(f"[结果] {result}\n")

        if _is_tool_error(result):
            _save_experience(action_name, action_args, result)
            print(f"[反思] 工具 {action_name} 返回错误，提示 LLM 换策略")
            result_msg = f"工具 {action_name} 返回了错误：{result}\n\n请反思失败原因，换一种方式重试。不要用完全相同的参数。"
        else:
            result_msg = f"工具返回：{result}"

        messages.append({"role": "user", "content": result_msg})
        full_history.append({
            "role": "user",
            "content": f"（工具 {action_name} 返回：{result}）"
        })
        messages = trim_messages(messages)

    fallback = "抱歉，我没有在限定步骤内完成这个任务。请尝试简化你的请求。"
    full_history.append({"role": "assistant", "content": fallback})
    return full_history


def run_agent_stream(user_input: str, max_rounds: int = 8,
                     conversation_history: list | None = None):
    """流式 Agent，yield 事件给 Gradio UI 逐字渲染

    事件类型：
      {"type": "token", "content": "..."}
      {"type": "tool_call", "name": "...", "args": {...}}
      {"type": "tool_result", "content": "..."}
      {"type": "done"}
    """
    system_prompt = build_system_prompt()
    messages = _prepare_messages(user_input, conversation_history)

    for _ in range(max_rounds):
        full_response = ""
        for token in call_llm_stream(messages, system_prompt=system_prompt):
            full_response += token
            yield {"type": "token", "content": token}

        response = full_response.strip()
        messages.append({"role": "assistant", "content": response})

        action = parse_action(response)
        if action is None:
            yield {"type": "done"}
            return

        action_name = action.get("action", "")
        action_args = action.get("args", {})

        if action_name == "final_answer":
            content = action.get("content", "")
            yield {"type": "final_answer", "content": content}
            yield {"type": "done"}
            return

        yield {"type": "tool_call", "name": action_name, "args": action_args}
        result = call_tool(action_name, action_args)
        yield {"type": "tool_result", "content": result}

        if _is_tool_error(result):
            _save_experience(action_name, action_args, result)
            result_msg = f"工具 {action_name} 返回了错误：{result}\n\n请反思失败原因，换一种方式重试。不要用完全相同的参数。"
        else:
            result_msg = f"工具返回：{result}"

        messages.append({"role": "user", "content": result_msg})
        messages = trim_messages(messages)

    for token in "抱歉，我没有在限定步骤内完成这个任务。":
        yield {"type": "token", "content": token}
    yield {"type": "done"}


# ── 终端测试 ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Agent 测试模式\n输入 'exit' 退出\n")
    conv_history = []
    while True:
        ui = input("你：")
        if ui.lower() in ("exit", "quit", "q"):
            break
        result = run_agent(ui, conversation_history=conv_history)
        last = ""
        for msg in reversed(result):
            if msg["role"] == "assistant" and msg["content"]:
                last = msg["content"]
                break
        print(f"\nAgent：{last}\n")
        conv_history.append({"role": "user", "content": ui})
        conv_history.append({"role": "assistant", "content": last})
        conv_history, summary = manage_memory(conv_history)
        if summary:
            print(f"[记忆] 已摘要旧对话并持久化")
        if len(conv_history) > 20:
            conv_history = conv_history[-20:]
