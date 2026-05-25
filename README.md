# AssistGen — 智能客服 Agent 项目

基于 **LangGraph + Neo4j + RAG** 构建的智能客服系统，支持自然语言查询商品知识图谱、多轮对话、文件/图片分析，并通过 Agent 自主决策完成复杂查询链路。

## 项目架构

```
用户输入
  └─ Router（问题分类）
       ├─ 闲聊 → LLM 直接回复
       ├─ 信息不足 → 追问用户（Guardrails 边界检查）
       ├─ 图片 → 视觉模型分析
       ├─ 文件 → 提取文本分析
       └─ 知识库查询 → KG 子图（核心）
              ├─ Guardrails（经营范围检查）
              ├─ Planner（任务分解）
              ├─ Tool Selection（Map：并行工具选择）
              │    ├─ Text2Cypher（LLM 生成 Cypher 查询 Neo4j）
              │    ├─ Predefined Cypher（高频查询预置）
              │    └─ GraphRAG（向量检索）
              ├─ Summarize（Reduce：汇总结果）
              └─ Final Answer
```

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python FastAPI + Pydantic + LangGraph |
| **大模型** | DeepSeek API / Ollama 本地模型（qwen2.5、deepseek-r1） |
| **知识图谱** | Neo4j 图数据库 |
| **RAG** | 向量检索 + Few-shot Cypher 示例 + LLM Query Rewrite + Rerank |
| **前端** | Vue 3 |
| **基础设施** | Redis 缓存、MySQL 持久化、Docker 部署 |

## 核心特性

- **Agent 自主决策**：LangGraph 编排多步骤工作流，Agent 根据问题自动选择工具
- **Text2Cypher**：LLM 根据自然语言生成 Cypher 查询语句，配合 Few-shot 示例和 LLM 校验
- **Guardrails 边界守卫**：判断用户问题是否在业务范围内，避免无效查询
- **Map-Reduce 并行处理**：Planner 拆解子任务，并行执行工具调用，汇总结果
- **多模态支持**：支持图片分析（视觉模型）和文件（PDF/文本）内容提取
- **缓存优化**：Redis 缓存覆盖 RAG 检索和模型调用结果，降低延迟

## 快速开始

### 前置依赖

- Python 3.10+
- Neo4j 数据库
- Redis（可选，缓存用）
- Ollama（可选，本地模型用）

### 安装

```bash
# 克隆仓库
git clone https://github.com/lgh88666/assistgen.git
cd assistgen

# 创建虚拟环境
cd "01_AssistGen 后端源码/fufan_deepseek_agent/llm_backend"
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 .\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env
# 编辑 .env 填入你的 API Key 和数据库配置
```

### 启动

```bash
uvicorn app.main:app --reload
```

API 默认运行在 `http://localhost:8000`。

## 项目结构

```
01_AssistGen 后端源码/fufan_deepseek_agent/llm_backend/
├── app/
│   ├── lg_agent/                # 智能客服 Agent 主模块
│   │   ├── lg_builder.py        # 主图构建（路由 + 节点编排）
│   │   ├── lg_states.py         # 状态定义
│   │   ├── lg_prompts.py        # 提示词模板
│   │   └── kg_sub_graph/        # KG 子图
│   │       ├── agentic_rag_agents/workflows/multi_agent/
│   │       │   └── multi_tool.py     # 子图入口（Map-Reduce 编排）
│   │       ├── agentic_rag_agents/components/
│   │       │   ├── guardrails/       # 边界检查
│   │       │   ├── planner/          # 任务分解
│   │       │   ├── tool_selection/   # 工具选择
│   │       │   ├── cypher_tools/     # Text2Cypher 生成与执行
│   │       │   ├── predefined_cypher/# 高频 Cypher 预置
│   │       │   └── customer_tools/   # GraphRAG 工具
│   │       └── ...
│   ├── core/                    # 核心配置
│   └── ...
├── 02_AssistGen 前端源码/        # Vue 3 前端
└── ...
```
