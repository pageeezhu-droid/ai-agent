"""
Gradio 网页界面 — ChatGPT 风格
侧边栏 260px + 主对话 768px · 浅色/深色双模式 · 所有元素显式设色
"""

import json as _json
import re as _re

import gradio as gr
from agent import run_agent_stream, manage_memory

CUSTOM_CSS = """
/* ── Reset ──────────────────────────────────────────────── */
*, *::before, *::after { outline: none !important; }
fieldset, [class*="gr-box"], [class*="gr-form"], [class*="gr-field"],
[class*="gr-input"], [class*="gr-button"], [class*="textbox"],
[class*="input"], [class*="wrapper"], [class*="container"], [class*="border"] {
    border: none !important; outline: none !important;
}
:root, .gradio-container, [class*="svelte"] {
    --border-color-primary: transparent !important;
    --input-border-color: transparent !important;
    --button-border-color: transparent !important;
    --block-border-color: transparent !important;
    --ring-color: transparent !important;
}
footer { display: none !important; }

/* ── Page ──────────────────────────────────────────────── */
html, body {
    background: #FAF9F6 !important;
    margin: 0 !important; padding: 0 !important;
    min-height: 100vh !important;
    color: #141413 !important;
}
.gradio-container {
    max-width: 100% !important; margin: 0 !important; padding: 0 !important;
    background: #FAF9F6 !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", sans-serif !important;
}
.app-layout {
    display: flex !important; min-height: 100vh !important; gap: 0 !important;
    border-top: 1px solid #E8E6E1 !important;
}

/* ── Sidebar — warm-toned, top-aligned ──────────────────── */
.sidebar {
    width: 240px !important; min-width: 240px !important; flex: none !important;
    background: #ffffff !important;
    padding: 48px 24px 32px !important;
    display: flex !important; flex-direction: column !important;
    justify-content: flex-start !important; gap: 4px !important;
    border-right: 1px solid #E8E6E1 !important;
    height: 100vh !important;
    align-self: flex-start !important;
}
.sidebar-brand {
    font-size: 22px !important; font-weight: 700 !important;
    color: #141413 !important; padding: 0 0 40px 0 !important;
    letter-spacing: -0.3px !important;
}
.sidebar-section {
    font-size: 11px !important; font-weight: 600 !important;
    color: #6B6966 !important; text-transform: uppercase !important;
    letter-spacing: 0.8px !important; padding: 24px 0 10px !important;
}

/* ── Memory status — plain text, no box ─────────────────── */
.memory-label, .memory-label label, .memory-label span,
.memory-label .label, .memory-label div, .memory-label * {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 4px 0 !important;
    color: #6B6966 !important; font-size: 13px !important;
    font-weight: 400 !important; margin: 0 !important;
}

/* ── Clear button ────────────────────────────────────────── */
.sidebar-btn {
    padding: 10px 24px !important; background: #F0EEE9 !important;
    border-radius: 20px !important; color: #6B6966 !important;
    font-size: 13px !important; font-weight: 500 !important;
    cursor: pointer !important; text-align: center !important;
    width: auto !important; border: none !important;
    transition: background 0.15s, color 0.15s !important;
    margin-top: 12px !important;
}
.sidebar-btn:hover {
    background: #E8E6E1 !important;
    color: #141413 !important;
}
.sidebar-btn * { color: inherit !important; }

/* ── Main Panel ──────────────────────────────────────────── */
.main-panel {
    flex: 1 !important; min-width: 0 !important;
    background: #FAF9F6 !important;
    display: flex !important; flex-direction: column !important;
    overflow: hidden !important;
    height: 100vh !important;
}
.chat-header {
    padding: 20px 32px !important;
    background: #ffffff !important;
    flex-shrink: 0 !important;
}
.chat-title { font-size: 16px !important; font-weight: 600 !important; color: #141413 !important; }

/* ── Chat area — flex col, fills remaining space ─────────── */
.chat-area {
    max-width: 720px !important; width: 100% !important;
    margin: 0 auto !important; flex: 1 1 0 !important;
    min-height: 0 !important;
    display: flex !important; flex-direction: column !important;
    gap: 20px !important;
    padding: 24px !important;
    overflow: hidden !important;
}

/* ── Chatbot — scrollable white card ────────────────────── */
.block.chat-main {
    background: #ffffff !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    flex: 1 1 0 !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    padding: 20px !important;
}
/* Override Gradio fixed height on the main chatbot block */
.block.chat-main[style*="height"] {
    height: auto !important;
}
.chatbot [class*="scroll"], .chat-main [class*="scroll"] {
    padding: 0 !important; gap: 8px !important;
    background: transparent !important;
}
/* Let bubble-wrap grow so parent chat-main handles scrolling */
.chat-main [class*="bubble-wrap"] {
    overflow: visible !important;
}

/* ── Input row + examples fixed at bottom ───────────────── */
.input-row, .examples {
    flex-shrink: 0 !important;
}

/* ── Messages — plain text, no bubbles ──────────────────── */
.message-row .user.message,
.message-row .bot.message,
.message-row .panel-full-width {
    background: transparent !important;
    border-radius: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
}
.message-row {
    max-width: 100% !important;
    word-break: break-word !important;
}
.message-row.user-row {
    text-align: right !important;
}
.message-row.bot-row {
    text-align: left !important;
}
.message-row, .message-row * {
    font-size: 14px !important;
    line-height: 1.65 !important;
    color: #141413 !important;
}
.message-row code {
    border-radius: 4px !important; padding: 2px 6px !important;
    font-size: 13px !important;
    font-family: "JetBrains Mono", "Cascadia Code", monospace !important;
    background: #F0EEE9 !important;
}

/* ── Kill inner chatbot prose card inside messages ───────── */
.message-content .chatbot,
.message-row .chatbot.prose,
.message-content .md.chatbot,
.message-row .md.prose,
.message-row span[class*="chatbot"] {
    background: transparent !important;
    padding: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    display: block !important;
}
.message-content {
    overflow: visible !important;
}
.bot.message, .user.message {
    overflow: visible !important;
}

/* ── Input — MD3 capsule card ────────────────────────────── */
.input-row {
    background: #ffffff !important;
    border-radius: 30px !important;
    border: 1px solid #E8E6E1 !important;
    padding: 12px 24px !important;
    margin: 0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
    display: flex !important; align-items: center !important; gap: 8px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.input-row:focus-within {
    border-color: #D97757 !important;
    box-shadow: 0 4px 12px rgba(217,119,87,0.15) !important;
}

.input-row textarea, .input-row input[type="text"] {
    background: transparent !important; border: none !important;
    padding: 4px 0 !important; font-size: 14px !important; color: #141413 !important;
    caret-color: #141413 !important; resize: none !important; flex: 1 !important;
}
.input-row textarea::placeholder { color: #999692 !important; font-size: 14px !important; opacity: 1 !important; }

button, button:focus, button:focus-visible { border: 0 !important; outline: none !important; }

/* ── Plus button ────────────────────────────────────────── */
.plus-btn {
    width: 48px !important; height: 36px !important;
    min-width: 48px !important; min-height: 36px !important;
    border-radius: 50% !important;
    margin-right: 8px !important;
    padding: 0 !important; font-size: 20px !important; font-weight: 300 !important;
    background: transparent !important; color: #6B6966 !important;
    cursor: pointer !important; display: flex !important; align-items: center !important;
    justify-content: center !important; transition: background 0.15s !important;
}
.plus-btn:hover { background: #F0EEE9 !important; color: #141413 !important; }
.plus-btn * { color: inherit !important; }

/* ── Send button ────────────────────────────────────────── */
.send-btn {
    background: #D97757 !important; color: #ffffff !important;
    border-radius: 50% !important;
    width: 40px !important; height: 40px !important;
    min-width: 40px !important; min-height: 40px !important;
    padding: 0 !important; font-size: 18px !important; font-weight: 500 !important;
    cursor: pointer !important; display: flex !important; align-items: center !important;
    justify-content: center !important;
    transition: background 0.15s, transform 0.15s !important;
    box-shadow: 0 1px 3px rgba(217,119,87,0.3) !important;
}
.send-btn:hover { background: #C5694A !important; transform: scale(1.05) !important; }
.send-btn:active { transform: scale(0.93) !important; }
.send-btn * { color: inherit !important; }

/* ── Examples — white card ───────────────────────────────── */
.examples {
    display: flex !important; flex-wrap: wrap !important;
    gap: 8px !important; justify-content: center !important;
    background: #ffffff !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    padding: 16px 20px !important;
    margin: 0 !important;
}
.examples button, .example, [class*="example"] button {
    background: #F0EEE9 !important;
    border: 1px solid transparent !important;
    border-radius: 16px !important;
    padding: 10px 20px !important; font-size: 14px !important;
    color: #6B6966 !important; font-weight: 500 !important;
    cursor: pointer !important; white-space: normal !important; text-align: center !important;
    transition: background 0.15s, color 0.15s, border-color 0.15s !important;
}
.examples button:hover, .example:hover, [class*="example"] button:hover {
    background: #ffffff !important;
    border-color: #E8E6E1 !important;
    color: #141413 !important;
}

/* ── Examples pagination ──────────────────────────────── */
[class*="paginate"] {
    display: flex !important; align-items: center !important;
    justify-content: center !important; gap: 6px !important;
    font-size: 0 !important;  /* hide "Pages:" text */
    margin-top: 4px !important;
}
[class*="paginate"] button {
    width: 8px !important; height: 8px !important;
    min-width: 8px !important; min-height: 8px !important;
    padding: 0 !important; font-size: 0 !important;
    border-radius: 50% !important;
    background: #E8E6E1 !important;
    border: none !important; cursor: pointer !important;
    transition: background 0.2s !important;
}
[class*="paginate"] button[class*="current-page"],
[class*="paginate"] button.current-page {
    background: #D97757 !important;
    width: 20px !important; min-width: 20px !important;
    border-radius: 10px !important;
}

/* ── Scrollbar ──────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px !important; }
::-webkit-scrollbar-track { background: transparent !important; }
::-webkit-scrollbar-thumb { background: #E8E6E1 !important; border-radius: 4px !important; }

/* ── Animation ──────────────────────────────────────────── */
.message-row .panel-full-width { animation: msgIn 0.2s ease-out !important; }
@keyframes msgIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* ── Thinking process — collapsible details ─────────────── */
.think-details {
    margin-bottom: 12px !important;
    border: 1px solid #E8E6E1 !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
    background: #FAF9F6 !important;
}
.think-details summary {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #6B6966 !important;
    cursor: pointer !important;
    user-select: none !important;
    padding: 2px 0 !important;
}
.think-details summary:hover {
    color: #141413 !important;
}
.think-log {
    margin-top: 8px !important;
    display: flex !important;
    flex-direction: column !important;
    gap: 6px !important;
}
.tk-text {
    font-size: 13px !important;
    color: #6B6966 !important;
    line-height: 1.5 !important;
}
.tk-call {
    font-size: 13px !important;
    color: #D97757 !important;
    font-weight: 500 !important;
    padding: 4px 10px !important;
    background: #FDF2EE !important;
    border-radius: 6px !important;
    border-left: 3px solid #D97757 !important;
}
.tk-result {
    font-size: 12px !important;
    color: #6B6966 !important;
    padding: 4px 10px !important;
    background: #F0EEE9 !important;
    border-radius: 6px !important;
    font-family: "JetBrains Mono", "Cascadia Code", monospace !important;
    max-height: 120px !important;
    overflow-y: auto !important;
    white-space: pre-wrap !important;
    word-break: break-all !important;
}
"""

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
