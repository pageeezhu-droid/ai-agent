# AI Agent

基于 DeepSeek API 的 AI Agent，采用 ReAct（Reasoning + Acting）范式，让 LLM 从"会说话"变成"能做事"。

## 特性

- **ReAct 循环**：思考 → 行动 → 观察，最多 8 轮自主决策
- **6 个工具**：计算器、网页搜索（360/搜狗/必应三引擎）、天气查询、文件读写、目录列表、Python 沙箱执行
- **流式输出**：SSE 逐 token 渲染，打字机效果
- **短期记忆**：保留最近 10 轮对话上下文
- **长期记忆**：自动摘要压缩 + memory.json 持久化，跨会话保留
- **自反思**：工具调用失败后分析原因、换策略重试，经验持久化到 experience.json
- **多 Agent 协作**：Critic Agent 审查回答质量（4 维度评估），自动修订改进，可切换开关
- **安全沙箱**：文件操作限制在 `workspace/` 目录，`run_python` 拦截危险模块
- **Web UI**：Gradio 界面，Claude 暖色系，思考过程可折叠，对话框独立滚动，Critic 审查可视化

## 架构

```
用户输入 → app.py (Gradio UI)
              ↓
         agent.py (ReAct 循环 + 自反思 + Critic)
              ↓              ↓
         llm_api.py     manage_memory()
         → DeepSeek     → 摘要压缩 → memory.json
              ↓
         tools.py → 执行工具 → 返回结果
              ↓
         结果喂回 LLM → 继续思考 → final_answer
              ↓
         Critic Agent → 审查 → 修订 → 最终回答
```

## 环境要求

- Python 3.10+
- DeepSeek API Key（设为环境变量 `DEEPSEEK_API_KEY`）

## 快速开始

```bash
cp .env.example .env          # 编辑 .env 填入 DeepSeek API Key
pip install -r requirements.txt
python app.py                  # 打开 http://localhost:17890
```

## 文件结构

```
ai-agent/
├── app.py              # Gradio Web UI
├── agent.py            # ReAct 循环 + Critic Agent
├── llm_api.py          # DeepSeek API 封装 (SSE 流式)
├── tools.py            # 7 个工具实现
├── style.css           # 自定义 CSS (Claude 暖色系)
├── .env.example        # API Key 配置模板
├── .gitignore
├── project-journey.md  # 完整开发过程记录
├── requirements.txt    # 依赖
└── workspace/          # 文件读写沙箱 + memory/experience 持久化
```

## 技术栈

- Python + DeepSeek-V3 API
- Gradio 6.x（自定义 CSS，Claude 暖色系）
- ReAct 范式 + CoT 思考链 + Few-shot Prompt
- 无第三方 Agent 框架（LangChain/LlamaIndex），从零搭建

