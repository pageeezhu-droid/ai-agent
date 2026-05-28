# AI Agent 框架 — 从构建到优化全过程

## 一、选题背景

选题一：AI Agent 框架搭建 —— 从"会说话"到"能做事"。

核心思想：让 LLM 学会"调用工具"和"自主决策"，从一个"会说话的模型"变成一个"能做事的智能体"。采用 ReAct 范式（Reasoning + Acting），让模型交替进行"思考"和"行动"。

**技术要求：**
- 从零搭建（禁止使用 LangChain、LlamaIndex 等高层框架）
- 至少 3 个工具
- 支持多轮"思考-行动"循环
- Python + DeepSeek API
- 加分项：流式输出、短期/长期记忆、Web UI、多 Agent 协作

---

## 二、系统架构

```
用户输入 → app.py (Gradio UI) / 终端
              ↓
         agent.py (ReAct 循环 + 自反思)
              ↓              ↓
         llm_api.py     manage_memory()
         → DeepSeek     → 摘要压缩 → memory.json
         (流式 SSE)     _is_tool_error()
              ↓              ↓
         agent.py       _save_experience()
         解析 JSON      → experience.json
              ↓
         tools.py → 执行工具 → 返回结果
              ↓
         结果喂回 LLM → 继续思考 → final_answer
```

### 项目文件结构

```
ai-agent/
├── app.py           ← Gradio 网页界面 (UI布局 + 自定义CSS + 事件绑定)
├── agent.py         ← ReAct 循环引擎 (系统提示词 + JSON解析 + 主循环)
├── llm_api.py       ← DeepSeek API 封装 (普通调用 + SSE流式)
├── tools.py         ← 6个工具的实现 + 注册表
├── requirements.txt ← 依赖：requests, gradio
└── workspace/       ← Agent 文件读写的安全沙箱
```

---

## 三、核心实现过程

### 3.1 ReAct 循环引擎 (`agent.py`)

**系统提示词设计：**

```
你是一个 AI 智能助手，你可以使用工具来解决用户的问题。
当前时间：2026年05月22日 15:30，星期五

## 可用工具
- calculate：执行数学计算
- search_web：搜索互联网获取实时信息
- get_weather：查询城市实时天气
- read_file：读取文件内容
- write_file：写入内容到文件
- list_files：列出工作目录下的文件

## 工作方式
1. **思考**：分析用户的问题，决定是否需要使用工具
2. **行动**：如果需要工具，输出 JSON 格式的指令
3. **观察**：等待工具执行结果
4. **循环**：根据结果决定下一步行动或给出最终答案

## 输出格式
需要使用工具时：{"action": "工具名", "args": {"参数名": "参数值"}}
准备好回答时：{"action": "final_answer", "content": "你的最终回答"}
```

**主循环逻辑：**

```python
for round_num in range(max_rounds):         # 最多 8 轮
    response = call_llm(messages)            # 1. 调 LLM
    action = parse_action(response)          # 2. 解析 JSON 指令
    
    if action["action"] == "final_answer":   # 3. 判断是否结束
        return action["content"]
    
    result = call_tool(action_name, args)    # 4. 执行工具
    messages.append(f"工具返回：{result}")    # 5. 结果喂回 LLM → 回到步骤 1
```

### 3.2 LLM API 封装 (`llm_api.py`)

- 基于 DeepSeek API（兼容 OpenAI 格式）
- 两种调用模式：
  - `call_llm()`：一次性返回完整响应（终端调试用）
  - `call_llm_stream()`：SSE 流式，逐 token yield（网页用）
- 解决 Windows 编码问题：`json.dumps(ensure_ascii=True)` + `data=payload_str.encode("utf-8")`

### 3.3 工具模块 (`tools.py`)

共实现 6 个工具，统一注册在 `TOOL_REGISTRY` 字典中：

| 工具 | 功能 | 实现方式 |
|------|------|----------|
| `calculate` | 数学计算 | `eval()` + 安全沙箱（限制 `__builtins__`） |
| `search_web` | 网页搜索 | 必应搜索 HTML 解析（国内可访问） |
| `get_weather` | 天气查询 | wttr.in 免费 API |
| `read_file` | 读取文件 | Python 内置 `open()` |
| `write_file` | 写入文件 | Python 内置 `open()` |
| `list_files` | 列出目录 | `os.listdir()` + 路径安全校验 |

**安全设计：** 所有文件操作限制在 `workspace/` 目录内，`_safe_path()` 函数防止路径穿越攻击。

### 3.4 JSON 解析 (`parse_action`)

LLM 回复格式多样，采用三层解析策略：

1. **代码块匹配：** 正则提取 `` ```json {...} ``` ``，用括号计数法处理嵌套花括号
2. **直接解析：** 尝试将整段响应作为 JSON 解析
3. **暴力裁剪：** 找到第一个 `{` 和对应闭合的 `}`，提取后解析

```python
def _extract_json(text):
    """括号计数法：正确处理嵌套 JSON"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
```

---

## 四、优化与加分项实现

### 4.1 流式输出（SSE）

**问题：** 网页需要打字机效果，而非等 LLM 全部生成完再显示。

**方案：**
- `llm_api.py` 新增 `call_llm_stream()`，设置 `stream: True`，逐行解析 SSE 数据
- `agent.py` 新增 `run_agent_stream()` 生成器，yield 结构化事件：
  - `{"type": "token", "content": "..."}` — 文本片段
  - `{"type": "tool_call", "name": "...", "args": {...}}` — 工具调用
  - `{"type": "tool_result", "content": "..."}` — 工具结果
  - `{"type": "done"}` — 任务完成
- `app.py` 中 `respond()` 函数消费这些事件，实时更新 Chatbot

### 4.2 短期记忆

**问题：** 每轮对话独立，Agent 不记得上一轮说了什么。

**方案：**
- 使用 `gr.State([])` 存储干净的对话历史（user/assistant 消息对，不含工具调用标记）
- 每次对话将历史传给 `run_agent_stream(conversation_history=...)`
- Agent 内部将历史消息前置到当前对话之前
- 最多保留 10 轮（20 条消息），超出自动裁剪最旧的

**效果：**
```
用户：我叫小明
Agent：你好小明！
用户：我叫什么名字？   ← Agent 记得"小明"
Agent：你叫小明。
```

### 4.3 时间感知

**问题：** LLM 训练数据有截止日期，不知道"今天"是几号。

**方案：** 在 `build_system_prompt()` 中动态注入当前日期：

```python
now = datetime.now().strftime("%Y年%m月%d日 %H:%M，星期%w")
# → "2026年05月22日 15:30，星期五"
```

### 4.4 Web UI 优化

**初版问题：** Gradio 默认紫色主题，风格陈旧。

**优化迭代（共 10+ 轮）：**

| 轮次 | 改动 | 问题 |
|------|------|------|
| 1 | 简单 CSS 覆盖 | 颜色不统一 |
| 2 | Apple 白色极简 | 系统深色模式 → 两侧深色 |
| 3 | 强制白底 `!important` | 和深色模式冲突 |
| 4 | 改为暗色 ChatGPT 风格 | 按钮白边 |
| 5 | 核弹级去边框（Svelte + ring 变量） | 白边消除 |
| 6 | 统一配色 `#1c1c1e` | 发送按钮颜色不统一 |
| 7 | 三个元素统一背景 | 输入框内部不一致 |
| 8 | textbox wrapper 透明 | 效果统一 |
| 9 | 按钮加粗、placeholder 调亮 | — |
| 10 | padding 调整 → 圆心对齐 | — |

**最终 UI 方案：**
- 纯黑/深灰统一配色：页面 `#1c1c1e`，输入栏/气泡 `#1c1c1e`
- 圆形发送按钮（42px），左侧 `+` 按钮（预留文件上传）
- 大圆角输入栏 pill（30px），气泡（24px）
- 系统字体栈（`-apple-system, "PingFang SC", ...`）
- 无 Gradio 默认紫色、无黑框、无白边

### 4.5 长文件写入修复

**问题：** Agent 无法写入长代码（如水仙花数程序）。

**根因分析：**
1. `max_tokens=2048` 不够容纳长代码 + JSON 结构
2. `parse_action` 的非贪婪正则 `\{.*?\}` 遇到嵌套 `{}` 会提前截断

**修复：**
- `max_tokens` 2048 → 8192
- 改用括号计数法（`_extract_json`）提取 JSON，正确处理嵌套花括号
- 系统提示词加 JSON 转义规则

### 4.6 中国网络适配

**问题：** Wikipedia 被墙、百度搜索 JS 渲染、DuckDuckGo 超时。

**解决：** 搜索改用必应（`bing.com`），天气用 wttr.in，两者国内可直连。

### 4.7 Prompt 优化（五合一）

**问题：** 原始 prompt 过于简单，缺少示例和约束。LLM 偶尔用错工具（如给 calculate 传 Python 代码）、不转义 JSON、直接凭知识回答而不调用工具。

**方案：** 同时实施 5 项优化：

| 优化 | 内容 |
|------|------|
| **1A 结构化工具描述** | 每个工具包含参数类型、返回格式、JSON 示例、警告（`tools.py:get_tool_descriptions()`） |
| **2A Few-shot 示例** | 系统提示词中加入 2 个完整 ReAct 对话示例（计算器 + 搜索保存） |
| **3A 禁止规则** | 明确禁止：Python 代码传入 calculate、"." 传入 read_file、不转义 JSON、臆造数据 |
| **4C JSON 转义强调** | 在提示词规则 + 工具描述两处强调转义规则（双引号 `\\"`、换行 `\\n`、反斜杠 `\\\\`） |
| **5A CoT 思考链** | 要求先输出「思考：...」行说明推理，再输出 JSON 指令 |

**改动的文件：**
- `agent.py`：SYSTEM_PROMPT 完全重写（从 ~20 行扩展至 ~70 行），加入 CoT、禁止规则、few-shot 示例
- `tools.py`：`get_tool_descriptions()` 改为逐工具结构化描述（功能 + 参数 + 返回 + 示例 + 警告）

**预期效果：**
- 工具调用更准确（结构化描述 + few-shot 消除歧义）
- JSON 转义错误减少（双重强调）
- 用户可见 CoT 思考过程（透明化推理）
- 减少"不调用工具直接回答"的情况（示例强化工具使用习惯）

### 4.8 Web UI 全面重设计

**问题：** 旧版 UI 布局紧凑（800px 容器、520px 聊天区）、所有元素同色（#1c1c1e）、无分区感、发送按钮无辨识度、示例区排列松散。

**方案：**

| 维度 | 改动 |
|------|------|
| **布局** | 容器 90% 宽 / max 1200px；聊天区 flex:1 占主体；输入区 + 示例区用 6%透明分隔线分区 |
| **输入栏** | 背景 #2a2a2d 比页面稍亮；focus-within 时边框变亮 + 蓝色微光；placeholder #808080 |
| **发送按钮** | 蓝色强调色 #4a9eff + hover 发光 + active 缩入动画 |
| **示例区** | CSS Grid 两列卡片布局；#252528 底色；hover 时文字变亮 + 边框高亮 |
| **文字层级** | 欢迎语 #a0a0a5（弱化）；辅助文字 #808080；用户气泡 #252528（与 AI 气泡 #1c1c1e 区分） |
| **底部栏** | 记忆状态简化为一句话；清除记忆改成文字按钮 |

**CSS 技术要点：**
- `.input-row:focus-within` 实现输入聚焦时整体发光
- `.examples` 用 `grid-template-columns: 1fr 1fr` 两列
- `.send-btn:hover` 用 `transform: scale(1.04)` 微放大
- 所有过渡统一 `0.2s ease` 保证手感一致

### 4.9 UI 层次感与交互反馈增强

**问题：** 页面一片"死黑"无层次；圆角不统一（8/14/24/30px 混用）；消息气泡无 hover 态，输入无 focus 反馈。

**方案：**

| 维度 | 改动 |
|------|------|
| **灰度分层** | 三层灰度：#1a1a1a（页面底）→ #1e1e1e（AI气泡/示例卡片）→ #252525（输入框）；用户气泡 #242424 居中 |
| **统一圆角** | 气泡/输入栏/示例卡片/底部按钮统一 12px；代码块 6px；圆形按钮保持 50% |
| **hover 反馈** | 消息气泡 hover 微上浮 + 背景变亮；示例卡片 hover 上浮 + 文字变白；清除按钮 hover 背景微亮 |
| **按钮三态** | 发送按钮 hover 放大 1.05 + 蓝色发光；active 缩至 0.94 + 深蓝；+ 按钮 hover 边框变亮 |
| **输入 focus** | `.input-row:focus-within` 边框 #4a4a4e + 蓝色微光环 + 背景微亮 #282828 |
| **Loading 动画** | 空 AI 气泡底部蓝色光标闪烁动画（blinkCursor 0.8s），提示"正在思考" |

### 4.10 代码执行工具（沙箱 run_python）

**问题：** Agent 无法运行 Python 代码或本地脚本，只能做单次工具调用。

**方案：** 新增 `run_python` 工具，在受限沙箱中执行 Python 代码。

| 维度 | 实现 |
|------|------|
| 执行引擎 | `exec()` + 受限 `__builtins__` |
| 超时控制 | daemon 线程 + `join(timeout=10)` |
| 输出捕获 | `sys.stdout` / `sys.stderr` 重定向到 `StringIO` |
| 文件安全 | `open()` 自动重定向到 workspace 沙箱（`_safe_path`） |
| 模块安全 | `__import__` 白名单：24 个安全模块（math/json/re/collections/itertools 等），拦截 os/shutil/subprocess/sys/pathlib |

**安全事件：** 初版未限制 `__import__`，Agent 写的 `organize_files.py` 通过 `import os, shutil` 将项目源文件移到了 `py_files/`、`txt_files/` 子目录，导致项目结构被破坏。

**修复：**
- 立即恢复项目文件到原始目录
- `__import__` 改为白名单机制，拦截所有危险模块
- 清理 workspace 中的肇事脚本

### 4.11 Web UI Galaxy 风格融合

**问题：** 旧版 UI 纯色 #1c1c1e，无层次感，所有元素融为一体。

**方案：** 从 GitHub 项目 [uiverse-io/galaxy](https://github.com/uiverse-io/galaxy)（6000+ 社区 UI 组件）中挑选 3 个暗色主题技术，适配到 #1c1c1e 底色：

| Galaxy 来源 | 技术 | 应用位置 |
|-------------|------|----------|
| **aadium** (neumorphism card) | 双面 box-shadow：暗影 `3px 3px 10px rgba(0,0,0,0.4)` + 亮反影 `-2px -2px 6px rgba(255,255,255,0.025)` | 输入栏、消息气泡、示例卡片 |
| **adamgiebl** (metallic button) | `linear-gradient(180deg, rgb(72,72,72)...)` 四段金属渐变 + `radial-gradient` 径向高光 + `repeating-conic-gradient` 噪点纹理 | 发送按钮（hover 反白发光） |
| **Lakshay-art** (glow border) | `:focus-within` 多层 `box-shadow` 外发光环 + `conic-gradient` 旋转边框概念（简化为静态 glow） | 输入栏 focus 状态 |

**布局微调：**
- 容器 800px → 960px
- 网格背景纹理（2rem 间距，径向渐变遮罩仅中央可见）
- 气泡 hover 微上浮 `translateY(-1px)`

### 4.12 JSON 框消除 — final_answer 纯文本化

**问题：** LLM 的 `final_answer` 输出为 JSON 格式 `{"action": "final_answer", "content": "..."}`，Gradio markdown 渲染为代码框，用户看到的是 JSON 而非回答文本。CoT 思考过程以大字体白色显示，视觉上掩盖了实际回答。

**方案：**

| 维度 | 实现 |
|------|------|
| agent.py | `run_agent_stream()` 在检测到 `final_answer` 时，新增 `{"type": "final_answer", "content": clean_text}` 事件 |
| app.py | `respond()` 接收 `final_answer` 事件，用干净 `content` 替换含 JSON 的 `buffer` |
| 效果 | 最终气泡只显示纯文本回答，JSON 代码框不再出现 |

### 4.13 Agent 自反思（Self-Reflection）

**问题：** 工具调用失败后，Agent 要么盲目重试相同参数，要么直接放弃。没有"分析失败原因→换策略"的能力。

**方案：**

| 维度 | 实现 |
|------|------|
| 错误检测 | `_is_tool_error(result)` 匹配 8 个中文错误关键词（错误/出错/失败/超时/不存在/未找到/状态码/没有权限） |
| 反思触发 | 检测到错误后，将标准"工具返回：{result}"替换为反思指令："请反思失败原因，换一种方式重试。不要用完全相同的参数。" |
| 经验持久化 | `_save_experience()` 将失败记录（工具名/参数/错误/时间戳）写入 `workspace/experience.json` |
| 经验注入 | `_load_experience_text()` 在 `build_system_prompt()` 时加载最近 3 条经验，注入系统提示词 |
| Prompt 强化 | 新增示例 4：read_file 失败→反思→list_files→告知用户；禁止规则改为"必须反思原因" |
| 适用范围 | `run_agent()`（终端）和 `run_agent_stream()`（Web）均生效 |

**效果验证：**
```
[1] read_file("hehe.txt") → 文件不存在
[反思] 提示 LLM 换策略
[2] list_files("") → 列出所有文件
[3] final_answer → 告知用户文件不存在，展示可用文件
```

### 4.14 长期记忆 — 对话摘要压缩

**问题：** 短期记忆仅保留最近 N 条消息，超出直接丢弃。用户在多轮对话中提到的个人信息、偏好、上下文在超出窗口后永久丢失。跨会话重启后全部遗忘。

**方案：** 不是简单"把偏好存 JSON"，而是**对话摘要 + 自动压缩**：

| 维度 | 实现 |
|------|------|
| 触发阈值 | `manage_memory()` 在对话超过 16 条时自动触发，保留最近 6 条 |
| 摘要引擎 | `_summarize_conversation()` 调用 LLM 将旧消息压缩为 ≤200 字摘要，提取姓名/身份/偏好/未完成任务/长期目标，忽略闲聊和已完成操作 |
| 持久化 | `_save_memory()` 追加摘要到 `workspace/memory.json`，最多保留 20 条，去重最新的 5 条注入 prompt |
| 注入 | `build_system_prompt()` 末尾附加长期记忆段："以下是此前对话中提取的关键信息"，LLM 优先参考 |
| 跨会话 | 重启服务后 `_load_memory()` 自动加载 memory.json，Agent 依然记得用户信息 |

**记忆流转：**
```
对话过长 → 触发 manage_memory()
  → _summarize_conversation(最旧10条) → LLM 压缩为摘要
  → _save_memory(摘要) → workspace/memory.json
  → _load_memory() → 注入下次 system prompt
```

---

### 4.15 搜索引擎重构（2026-05-25）

**问题链条：**
1. 初始使用 Bing → "周杰伦2026新专辑" 返回「周（汉语汉字）」等词典释义（Bing 中文索引差，查询分词错误）
2. 尝试百度 → 桌面版 JS 渲染不可解析，移动版触发验证码
3. 改用搜狗(sogou.com) → 单次测试正常，Agent 连续 4+ 次调用后返回 403/反爬页面
4. 搜狗返回空结果 → 代码 fallback 到 Bing → 再次返回词典垃圾

**最终方案：三引擎级联**

```
360 搜索 (so.com)  ──主引擎──→  中文查询首选，H3 解析，无频控
     ↓ 失败
搜狗 (sogou.com)   ──备选──→  Session 复用 Cookie，403 → 重建 Session
     ↓ 失败
必应 (bing.com)    ──兜底──→  30+ 词典特征词过滤（简繁体），b_algo 块解析
     ↓ 失败
返回"未找到相关信息，请换搜索词"
```

**新增函数：**
- `_search_360(query)` — 360 搜索主引擎，解析 H3 标签
- `_search_sogou(query)` — 搜狗搜索，带 Session 管理、403 检测重建、1.8s 频率控制、反爬 UA 轮换
- `_search_bing_smart(query)` — 必应搜索，30+ 简繁体词典特征词过滤 (`_BING_JUNK_KW`)
- `_is_blocked(html)` — 搜狗反爬检测（验证码/antispider/小页面）
- `_is_junk_result(text)` — 必应词典垃圾检测
- `search_web(query)` — 统一入口，三引擎级联调用

**效果验证：**
- 7 组测试查询（含中英文、不同空格格式）全部返回正确结果
- Agent 查询"周杰伦2026年新专辑"正确回答《太阳之子》13 首歌 3 月 25 日上线
- 平均响应 0.7s/查询

---

### 4.16 UI 配色切换：Google MD3 → Claude 暖色系（2026-05-27）

**问题：** 旧版暗色 #1c1c1e 配色与 DeepSeek/Claude 品牌不匹配，用户偏好暖色方案。

**方案：** 全面替换为 Claude 暖色系：

| 色值 | 用途 |
|------|------|
| `#FAF9F6` | 页面底色 |
| `#ffffff` | 卡片/侧边栏 |
| `#141413` | 主文字 |
| `#6B6966` | 辅助文字 |
| `#D97757` | 强调色（发送按钮、hover） |
| `#E8E6E1` | 边框 |
| `#F0EEE9` | 浅填充（代码块、示例按钮） |

`preview.html` 同步更新为独立 CSS 预览文件，方便快速迭代。

### 4.17 气泡组件排查与重构（2026-05-27）

**问题：** Gradio 6.x Chatbot 默认 `layout="bubble"`，内部 DOM 嵌套复杂：
```
.message-row → .bot.message (白色背景+阴影+圆角) → .message-content
  → span.chatbot.prose (白色背景+padding+圆角+阴影)
```
两层白色卡片叠加，导致文字被遮挡、圆角失效。

**排查过程：**
1. 尝试 `.bubble-wrap` / `[data-testid]` 等多种选择器，均未命中正确的 DOM 层级
2. 使用 Playwright 无头浏览器 dump 真实 DOM 结构，确认 `.bot.message` 和 `span.chatbot.prose` 两层遮挡
3. Playwright 脚本遇到 SVG `className` 为 `SVGAnimatedString` 对象的问题，修复为 `typeof el.className === 'string'` 判断

**方案：**

| 层级 | 修复 |
|------|------|
| `.bot.message` / `.user.message` | `background: transparent; border-radius: 0; padding: 0; box-shadow: none` |
| `.panel-full-width` | 同上 |
| `span.chatbot.prose`（内层） | `background: transparent; padding: 0; border-radius: 0; box-shadow: none; display: block` |
| `.message-content` | `overflow: visible` |

**效果：** 消息以纯文本显示，用户/机器人左右对齐，无任何气泡遮挡。

### 4.18 对话框独立滚动 + 输入栏固定（2026-05-27）

**问题：** `.main-panel` 设置 `overflow-y: auto`，导致整个右侧面板（标题栏+聊天区+输入区+示例区）一起滚动。对话增多时输入栏被推出视野。

**方案：**

| 元素 | CSS 改动 |
|------|----------|
| `.main-panel` | `overflow-y: auto` → `overflow: hidden; height: 100vh` |
| `.chat-area` | `flex: 1 1 0; min-height: 0; overflow: hidden` |
| `.block.chat-main` | `flex: 1 1 0; min-height: 0; overflow-y: auto; height: auto !important`（覆盖 Gradio 内联 `height: 480px`） |
| `.chat-main [class*="bubble-wrap"]` | `overflow: visible !important`（消除 Gradio 嵌套滚动容器） |
| `.input-row, .examples` | `flex-shrink: 0`（固定在底部） |

**验证：** Playwright 测试 `scrollHeight=1030 > clientHeight=412`，`scrollTop` 可程序化滚动。主面板 `overflow-y=hidden`，页面级滚动被阻断。

### 4.19 思考过程可折叠组件 + 最终回答提取（2026-05-27）

**问题：**
1. CoT 思考文本（"思考：..."、JSON 代码块）和最终回答混在同一个气泡，思考过程冗长遮挡答案
2. `final_answer` 的 JSON 不在 ` ``` ``` ` 代码块内时，`_strip_json` 正则无法匹配，用户看到 `{"action": "final_answer", "content": "..."}` 原始 JSON

**方案：**

| 维度 | 实现 |
|------|------|
| 事件分流 | `respond()` 区分 5 种事件：token → `thinking_buf`；tool_call/tool_result → `thinking_steps[]`；final_answer → `clean_answer` |
| HTML 结构 | `<details class="think-details"><summary>思考过程 (N 步)</summary>...</details>` + 下方干净回答 |
| JSON 剥离 | `_strip_json()` 升级：正则移除 ` ```json ``` ` 块 + 括号计数法移除 `{"action":...}` 裸 JSON 对象 |
| 兜底提取 | `_try_extract_answer()` 使用括号计数法 + `json.loads`，即使 `final_answer` 事件未触发也能从 buffer 提取 `content` 字段 |
| CSS 样式 | `.think-details` 暖灰边框卡片；`.tk-call` 赤土色高亮；`.tk-result` 等宽字体可滚动（max-height 120px） |

**效果：** 思考过程默认折叠，点击展开查看细节；最终回答始终以干净 Markdown 显示在气泡中，无 JSON 泄漏。

### 4.20 Examples 轮换 + 侧边栏顶对齐（2026-05-27）

**问题：** Examples 只有 4 条固定示例，缺乏多样性；侧边栏内容垂直居中，不符合导航习惯。

**方案：**

| 维度 | 改动 |
|------|------|
| Examples 扩展 | 4 条 → 16 条，覆盖计算/搜索/天气/文件/翻译/Python/知识问答等场景 |
| 翻页 | `examples_per_page=6`，圆点分页器（当前页赤土色宽点，其余暖灰圆点） |
| 分页 CSS | `[class*="paginate"]` 容器 `font-size: 0`（隐藏 "Pages:" 文字）+ 按钮改为 8px 圆点 |
| 侧边栏对齐 | `justify-content: center` → `flex-start`，`padding-top: 48px` |
| 侧边栏按钮 | 黑色 `#141413` → 暖灰 `#F0EEE9` 文字 `#6B6966`，hover 变 `#E8E6E1` + 文字 `#141413` |

---

## 五、当前项目状态

### 功能清单

| 功能 | 状态 |
|------|------|
| ReAct 循环 | ✓ |
| 流式输出 (SSE) | ✓ |
| 短期记忆 (10 轮) | ✓ |
| 时间感知 | ✓ |
| Prompt 优化 (五合一) | ✓ |
| Web UI (Gradio, Claude 暖色系) | ✓ |
| 计算器 | ✓ |
| 网页搜索 (360+搜狗+必应三引擎) | ✓ |
| 天气查询 (wttr.in) | ✓ |
| 文件读取 | ✓ |
| 文件写入 | ✓ |
| 目录列表 | ✓ |
| Python 代码执行 (沙箱) | ✓ |
| Agent 自反思 (经验库) | ✓ |
| 长期记忆 (摘要压缩) | ✓ |
| 安全沙箱 (workspace/) | ✓ |
| 思考过程可折叠组件 | ✓ |
| 对话框独立滚动 (输入固定) | ✓ |
| Examples 轮换 (16条, 分页) | ✓ |
| 多 Agent 协作 (Critic) | ✗ |
| 文件上传 (预留 `+` 按钮) | ✗ |

### 关键参数

| 参数 | 值 |
|------|------|
| LLM | DeepSeek-V3 (deepseek-chat) |
| max_tokens | 8192 |
| temperature | 0.1 |
| 最大 ReAct 轮次 | 8 |
| 短期记忆轮数 | 10 |
| UI 端口 | 17890 |
| UI 配色 | Claude 暖色系 (#FAF9F6 / #D97757 / #E8E6E1) |
| 示例数量 | 16 条, 6 条/页 |

---

## 六、遇到的典型问题与解决

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API 请求 400 错误 | Windows JSON 序列化产生非法 surrogate 字符 | `json.dumps(ensure_ascii=True)` + byte 编码 |
| 终端中文乱码 | Windows GBK 编码 | `PYTHONIOENCODING=utf-8` |
| 搜索工具超时 | 百度/Wikipedia/DDG 国内不可用 | 改用必应搜索 |
| Agent 无限循环 | LLM 输出不含 JSON 工具调用 | 将 `parse_action=None` 视为 final_answer |
| 长文件写入失败 | max_tokens 不够 + 嵌套 JSON 截断 | 8192 tokens + 括号计数法 |
| Gradio 6.x 兼容性 | theme/css 参数位置变更 | theme 移到 `launch()`，Chatbot 改用 dict 格式 |
| 系统深色模式冲突 | 网页白色 vs 系统暗色割裂 | 改为 ChatGPT 暗色风格，统一纯黑/深灰 |
| 按钮白边 | Gradio Svelte 组件 focus ring | 覆盖 `--ring-*` CSS 变量 + `[class*="svelte"]` 去边框 |
| 布局紧凑+无分区感 | 800px容器+所有元素同色 | 宽容器 90%/1200px + 分隔线 + 卡片网格 + 蓝色发送按钮 |
| Agent 破坏项目结构 | `run_python` 无 import 限制 | `__import__` 改为白名单，拦截 os/shutil/subprocess 等危险模块 |
| `run_python` 进程挂起不退出 | 超时线程非 daemon | 设置 `daemon=True` |
| 最终回答显示为 JSON 代码框 | LLM 输出 `final_answer` JSON 原样渲染 | agent yield 干净 `content` + app 用干净文本替换 buffer |
| 工具失败后 Agent 盲目重试 | 无失败检测+反思机制 | `_is_tool_error()` 8 关键词检测 + 反思 prompt + 经验库持久化 |
| 长期对话丢失上下文 | 短期记忆超限直接丢弃旧消息 | `manage_memory()` 自动摘要压缩 + memory.json 持久化 + 跨会话加载 |
| 搜索返回词典释义 | Bing 中文索引差，搜狗 403 限频 | 三引擎级联：360 → 搜狗(带 Session) → 必应(词典过滤) |
| Chatbot 气泡多层重叠遮挡文字 | Gradio 6.x 默认 `.bot.message` + `span.chatbot.prose` 两层白色卡片 | Playwright DOM 排查 + 逐层 `background: transparent` |
| 对话框滚动带动整个页面 | `.main-panel` 整体 `overflow-y: auto` | flex 布局隔离：仅 `.chat-main` 可滚动，其余 `flex-shrink: 0` |
| CoT 思考过程占据主气泡 | 所有 token 混入同一 buffer | 事件分流 + `<details>` 可折叠组件 |
| 裸 JSON（无代码块）泄漏到回答 | `_strip_json` 仅匹配 ` ``` ` 格式 | 括号计数法移除裸 JSON + `_try_extract_answer` 兜底提取 |

---

## 七、待完成的优化方向

1. **`+` 按钮功能：** 实现文件上传读取
2. **多 Agent 协作（Critic Agent）：** 对抗式双 Agent：主 Agent 回答 → Critic 挑刺 → 主 Agent 修订
3. **Workspace 可视化：** Web UI 侧边栏实时显示文件树

---

## 八、启动方式

```bash
cd ai-agent
pip install -r requirements.txt
python app.py
# 打开 http://localhost:17890
```
