"""
Gradio 网页界面 — ChatGPT 风格
侧边栏 260px + 主对话 768px · 浅色/深色双模式 · 所有元素显式设色
"""

import json as _json
import re as _re

import gradio as gr
from agent import run_agent_stream, manage_memory

CUSTOM_CSS = open("style.css", encoding="utf-8").read()

# ── Logic ────────────────────────────────────────────────

def _extract_json_obj(text: str) -> str | None:
    """Bracket-counting: extract first complete {} JSON object from text."""
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


def _strip_json(text: str) -> str:
    """Remove JSON code blocks and raw JSON objects from thinking text."""
    # 1) Remove ```json ... ``` fenced blocks
    text = _re.sub(r'```(?:json)?\s*.*?```', '', text, flags=_re.DOTALL)
    # 2) Remove raw {"action":...} JSON objects (bracket-counting)
    while True:
        obj = _extract_json_obj(text)
        if obj is None:
            break
        try:
            parsed = _json.loads(obj)
            if isinstance(parsed, dict) and "action" in parsed:
                text = text.replace(obj, "", 1)
                continue
        except Exception:
            pass
        break
    return text.strip()


def _try_extract_answer(text: str) -> str | None:
    """If text contains a final_answer JSON, extract the content field."""
    obj = _extract_json_obj(text)
    if obj:
        try:
            parsed = _json.loads(obj)
            if isinstance(parsed, dict) and parsed.get("action") == "final_answer":
                return parsed.get("content", "")
        except Exception:
            pass
    return None

def _build_message(thinking_steps: list, thinking_buf: str, answer: str) -> str:
    """Build assistant message: collapsible thinking + visible answer."""
    parts = []

    # Build thinking log HTML
    log = ""
    for kind, content in thinking_steps:
        if kind == "thinking":
            clean = _strip_json(content)
            if clean:
                log += f'<div class="tk-text">{_escape_html(clean)}</div>'
        elif kind == "tool_call":
            log += f'<div class="tk-call">调用工具: {_escape_html(content)}</div>'
        elif kind == "tool_result":
            short = content[:300] + ("…" if len(content) > 300 else "")
            log += f'<div class="tk-result">{_escape_html(short)}</div>'

    # Current round thinking (not yet concluded)
    if thinking_buf.strip():
        clean = _strip_json(thinking_buf)
        if clean:
            log += f'<div class="tk-text">{_escape_html(clean)}</div>'

    if log:
        step_count = sum(1 for s in thinking_steps if s[0] == "tool_call")
        parts.append(f'<details class="think-details"><summary>思考过程 ({step_count} 步)</summary><div class="think-log">{log}</div></details>')

    if answer:
        parts.append(answer)
    elif not log:
        parts.append("…")

    return "\n\n".join(parts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def respond(message: str, history: list, agent_history: list):
    if not message.strip():
        return history, agent_history

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": ""})
    yield history, agent_history

    thinking_steps = []   # [(kind, content), ...]
    thinking_buf = ""     # current round token buffer
    clean_answer = None

    for event in run_agent_stream(message, conversation_history=agent_history):
        if event["type"] == "token":
            thinking_buf += event["content"]
            history[-1] = {"role": "assistant", "content": _build_message(thinking_steps, thinking_buf, clean_answer or "")}
            yield history, agent_history

        elif event["type"] == "tool_call":
            thinking_steps.append(("thinking", thinking_buf))
            thinking_steps.append(("tool_call", event["name"]))
            thinking_buf = ""
            history[-1] = {"role": "assistant", "content": _build_message(thinking_steps, "", clean_answer or "")}
            yield history, agent_history

        elif event["type"] == "tool_result":
            thinking_steps.append(("tool_result", event["content"]))
            history[-1] = {"role": "assistant", "content": _build_message(thinking_steps, thinking_buf, clean_answer or "")}
            yield history, agent_history

        elif event["type"] == "final_answer":
            # Remaining buffer is last round's thinking + JSON, not answer
            if thinking_buf.strip():
                thinking_steps.append(("thinking", thinking_buf))
            thinking_buf = ""
            clean_answer = event["content"]
            history[-1] = {"role": "assistant", "content": _build_message(thinking_steps, "", clean_answer)}
            yield history, agent_history

        elif event["type"] == "done":
            break

    # Finalize
    if clean_answer:
        visible = clean_answer
    elif thinking_buf.strip():
        # Try extracting from raw final_answer JSON
        extracted = _try_extract_answer(thinking_buf)
        if extracted:
            visible = extracted
            # Move raw JSON from buffer into thinking steps
            thinking_steps.append(("thinking", thinking_buf))
        else:
            visible = _strip_json(thinking_buf)
    else:
        visible = ""

    final_content = _build_message(thinking_steps, "", visible)
    history[-1] = {"role": "assistant", "content": final_content}

    agent_history.append({"role": "user", "content": message})
    agent_history.append({"role": "assistant", "content": visible})

    agent_history, summary = manage_memory(agent_history)
    if summary:
        print(f"[记忆] 已摘要旧对话并持久化")

    yield history, agent_history


def clear_memory():
    return [{"role": "assistant", "content": "你好，有什么可以帮你？"}], [], ""


def get_memory_status(agent_history: list):
    if not agent_history:
        return ""
    turns = len(agent_history) // 2
    return f"已记忆 {turns} 轮对话"


# ── UI ────────────────────────────────────────────────────

WELCOME = [{"role": "assistant", "content": "你好，有什么可以帮你？"}]

with gr.Blocks(title="AI Agent") as demo:

    agent_state = gr.State([])

    with gr.Row(equal_height=False, elem_classes="app-layout"):
        # ── Sidebar ──
        with gr.Column(elem_classes="sidebar"):
            gr.HTML('<div class="sidebar-brand">AI Agent</div>')
            gr.HTML('<div class="sidebar-section">对话</div>')
            memory_label = gr.Label(value="", elem_classes="memory-label")
            clear_btn = gr.Button("清除对话", elem_classes="sidebar-btn")

        # ── Main panel ──
        with gr.Column(elem_classes="main-panel"):
            # Header
            with gr.Row(elem_classes="chat-header"):
                gr.HTML('<span class="chat-title">AI Agent</span>')

            # Centered chat area
            with gr.Column(elem_classes="chat-area"):
                chatbot = gr.Chatbot(height=480, value=WELCOME, elem_classes="chat-main")

                # Input row (defined before Examples so msg exists)
                with gr.Row(elem_classes="input-row", equal_height=True):
                    plus_btn = gr.Button("+", elem_classes="plus-btn", scale=0)
                    msg = gr.Textbox(
                        placeholder="输入消息…",
                        scale=1,
                        container=False,
                        show_label=False,
                    )
                    submit = gr.Button("↑", elem_classes="send-btn", scale=0)

                # Examples
                gr.Examples(
                    examples=[
                        "爱因斯坦哪年出生？活了多少岁？",
                        "杭州今天天气如何？写入 weather.txt",
                        "搜索量子计算最新进展并保存到 quantum.txt",
                        "计算 123456 × 789012",
                        "列出当前目录下所有文件",
                        "用 Python 生成 1 到 100 的质数，保存到 primes.txt",
                        "北京到上海的距离是多少公里？",
                        "写一首关于人工智能的五言诗，保存到 ai_poem.txt",
                        "搜索 2026 年诺贝尔奖得主",
                        "计算 (3.14159 × 2.71828) / 1.414",
                        "帮我创建一个 todo.txt，列出 5 件今天要做的事",
                        "斐波那契数列第 30 项是多少？",
                        "伦敦现在的天气如何？",
                        "帮我把 'Hello World' 翻译成 5 种语言",
                        "计算 2 的 64 次方",
                        "搜索马斯克的星舰最新发射消息",
                    ],
                    examples_per_page=6,
                    inputs=msg,
                )

    # ── Events ──
    send_event = gr.on(
        triggers=[msg.submit, submit.click],
        fn=respond,
        inputs=[msg, chatbot, agent_state],
        outputs=[chatbot, agent_state],
        queue=True,
    )
    send_event.then(lambda: "", None, msg)
    send_event.then(get_memory_status, [agent_state], [memory_label])

    clear_btn.click(
        fn=clear_memory,
        inputs=[],
        outputs=[chatbot, agent_state, memory_label],
    )


if __name__ == "__main__":
    print("http://localhost:17890")
    demo.launch(
        server_name="127.0.0.1",
        server_port=17890,
        share=False,
        css=CUSTOM_CSS,
    )
