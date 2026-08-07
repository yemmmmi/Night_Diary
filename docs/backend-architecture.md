# 夜话日记后端架构说明

> 本文档解析 `server/app/` 后端的分层架构、各模块与文件职责、调用关系及降级策略。

---

## 1. 项目概述

### 1.1 技术栈

| 层面 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x |
| 数据库 | SQLite（默认）/ MySQL（生产可选） |
| 向量数据库 | ChromaDB（日记/卡片语义检索） |
| 图数据库 | Neo4j（实体关系图，可选） |
| 缓存 | Redis（会话/JWT黑名单/模型配置缓存，可选） |
| 任务队列 | RQ（异步实体提取等，可选） |
| AI 编排 | LangGraph（对话状态图）+ 自研多智能体图 |
| LLM 接入 | OpenAI 兼容协议（多 provider、分层级路由） |
| 认证 | JWT + OAuth2 Password Flow |

### 1.2 架构模式

采用**分层架构**，自上而下六层：

```
api          → HTTP 路由层（请求/响应 Schema、依赖注入、错误处理）
services     → 服务编排层（业务流程编排、AI 场景入口、依赖容器）
domain       → 领域核心层（多智能体、记忆系统、RAG、技能、反馈学习）
infrastructure → 基础设施层（数据库、ORM 模型、外部服务适配器）
shared       → 共享基础设施（LLM 协议、错误体系、追踪接口、工具函数）
workers      → 后台任务层（RQ Worker 入口）
```

### 1.3 两大 AI 场景

| 场景 | 入口 | 编排器 | 执行引擎 |
|------|------|--------|----------|
| 场景一：日记分析 | `analysis_service.py` | `DiaryOrchestrator` | `ExecutionPlanner` + `MultiAgentGraph` |
| 场景二：多轮对话 | `conversation_ai_service.py` | `ConversationOrchestrator` | `ConversationLoop` + `ConversationGraph` |

两个场景共享：危机检测、记忆网关、实体提取、上下文压缩等子组件，通过统一的 `OrchestratorProtocol` 接口暴露。

---

## 2. 目录结构

```
server/app/
├── __init__.py                  # 包初始化
├── config.py                    # 应用配置（Pydantic Settings）
├── main.py                      # FastAPI 应用入口
│
├── api/                         # API 路由层
│   ├── __init__.py
│   ├── deps.py                  # 依赖注入（容器/会话/用户）
│   ├── mappers.py               # ORM → Schema 映射
│   ├── schemas.py               # 请求/响应模型
│   └── v1/                      # v1 版本端点
│       ├── router.py            # 路由聚合
│       ├── analysis.py          # 日记分析
│       ├── auth.py              # 认证
│       ├── card.py              # 记忆卡片
│       ├── conversation.py      # 对话
│       ├── dev.py               # 开发者模式
│       ├── diary.py             # 日记 CRUD
│       ├── error_handlers.py    # 全局错误处理
│       ├── export.py            # 数据导出
│       ├── feedback.py          # 反馈
│       ├── memory.py            # 记忆管理
│       ├── model_download.py    # 模型下载
│       ├── models.py            # 模型配置
│       ├── stats.py             # 统计
│       ├── tags.py              # 标签
│       └── weekly.py            # 周记
│
├── domain/                      # 领域核心层
│   ├── orchestrator.py          # 编排器协议（统一两大场景接口）
│   ├── agents/                  # 多智能体系统（15 个文件）
│   ├── feedback/                # 反馈学习（5 个文件）
│   ├── knowledge/               # 领域知识（3 个文件）
│   ├── memory/                  # 记忆系统（7 个文件）
│   ├── rag/                     # 检索增强生成（9 个文件）
│   └── skills/                  # 技能系统（10 个文件）
│
├── infrastructure/              # 基础设施层
│   ├── database.py              # SQLAlchemy 引擎/会话
│   ├── auth.py                  # JWT 认证
│   ├── security.py              # API Key 加密
│   ├── redis_client.py          # Redis 客户端
│   ├── task_queue.py            # 任务队列
│   ├── entity_graph.py          # 实体关系图
│   ├── *_tracer.py              # 各类追踪器
│   ├── *_repository.py          # 各类仓库
│   └── models/                  # ORM 模型（17 个表模型）
│
├── services/                    # 服务编排层
│   ├── container.py             # 依赖注入容器
│   ├── analysis_service.py      # 场景一入口
│   ├── conversation_ai_service.py # 场景二入口
│   ├── diary_service.py         # 日记 CRUD
│   ├── memory_gateway.py        # 记忆网关
│   ├── ...                      # 其他业务服务
│   └── ai/                      # AI 执行引擎（13 个文件）
│
├── shared/                      # 共享基础设施
│   ├── llm.py                   # LLM 客户端协议
│   ├── llm_factory.py           # LLM 工厂
│   ├── errors.py                # 统一错误体系
│   ├── tracing.py               # 追踪接口
│   ├── pipeline_trace.py        # 管道追踪
│   ├── crisis_guard.py          # 危机守卫
│   └── ...                      # 其他共享工具
│
└── workers/                     # 后台任务
    └── worker.py                # RQ Worker 入口
```

---

## 3. 模块职责

### 3.1 api 层

负责 HTTP 请求/响应的边界处理：

- **路由定义**：`v1/` 下各端点文件定义具体的 RESTful 路由，通过 `router.py` 聚合后挂载到 FastAPI 应用
- **依赖注入**：`deps.py` 提供容器、数据库会话、当前用户、用户上下文的依赖注入函数
- **数据映射**：`mappers.py` 将 ORM 行对象转换为响应 Schema；`schemas.py` 定义 Pydantic 请求/响应模型
- **错误处理**：`error_handlers.py` 注册全局异常处理器，将领域错误转换为 HTTP 响应

### 3.2 domain 层

系统的核心业务逻辑，纯 Python 实现，不依赖具体框架：

- **agents（多智能体系统）**：Supervisor 中枢负责意图分类、技能选择、路由决策和回复合成；Empathy/Retrieval/Insight 三个 Worker 并发执行；ContextCompressor 压缩上下文窗口
- **memory（记忆系统）**：三层记忆架构——工作记忆（当前会话）、情景记忆（近期事件，deque + SQLite）、长期记忆（用户画像，基于标签的晋升机制）
- **rag（检索增强生成）**：混合检索器集成 BM25 关键词检索 + ChromaDB 向量检索 + 重排序；支持日记集合和卡片集合
- **skills（技能系统）**：可插拔的技能架构，含危机检测、情感分析、实体追踪、记忆回忆等技能；通过注册表统一管理和激活
- **feedback（反馈学习）**：基于汤普森采样的多臂赌博机实现提示词风格调优；支持隐式风格偏好提取
- **knowledge（领域知识）**：领域知识存储，为智能体提供常识背景

### 3.3 infrastructure 层

外部服务适配与持久化实现：

- **数据库**：`database.py` 提供 SQLAlchemy 引擎和会话工厂，支持 SQLite/MySQL 双引擎切换，含轻量级迁移
- **ORM 模型**：`models/` 下 17 个表模型对应数据库表结构
- **外部服务适配**：Redis 客户端、Neo4j 实体图、RQ 任务队列、MCP 服务器等
- **追踪器**：LLM 调用追踪、Agent 决策追踪、技能激活追踪，均基于 SQLite 持久化
- **认证安全**：JWT 签发/解码/黑名单、API Key 加密/解密

### 3.4 services 层

业务流程编排，连接 api 层和 domain 层：

- **依赖容器**：`ServiceContainer` 是核心，管理所有长生命周期依赖，提供分阶段启动（核心 → AI 栈）
- **AI 场景入口**：`analysis_service.py`（场景一）和 `conversation_ai_service.py`（场景二）是两大 AI 流程的入口
- **业务服务**：日记 CRUD、对话管理、记忆网关、卡片服务、统计、导出、周记等
- **AI 执行引擎**：`ai/` 子模块包含执行规划器、Agent 执行器、链式执行器、对话图等

### 3.5 shared 层

跨模块共享的基础设施：

- **LLM 协议**：定义 LLM 客户端协议和工厂，支持多 provider、分层级路由
- **错误体系**：`AppError` 异常体系，统一领域错误类型
- **追踪接口**：定义 LLM/Agent/Skill 可观测性端口和记录类型
- **工具函数**：Token 计算、嵌入构建、危机守卫、情感评估等

### 3.6 workers 层

后台任务执行入口，基于 RQ 实现异步任务（如实体提取），支持线程降级。

---

## 4. 关键文件功能表

### 4.1 根级

| 文件 | 职责 |
|------|------|
| `config.py` | 应用配置（Pydantic Settings），环境变量加载，路径/数据库/Redis/Neo4j/MCP/安全/LLM 配置项 |
| `main.py` | FastAPI 应用入口，CLI 参数解析，CORS 中间件，生命周期管理（核心+AI 双阶段启动），健康检查端点 |

### 4.2 api 模块

| 文件 | 职责 |
|------|------|
| `api/deps.py` | FastAPI 依赖注入（容器/DB会话/当前用户/用户上下文） |
| `api/mappers.py` | ORM 行到响应 Schema 的映射转换 |
| `api/schemas.py` | Pydantic 请求/响应模型定义 |
| `api/v1/router.py` | v1 路由聚合器 |
| `api/v1/analysis.py` | 日记分析触发接口 |
| `api/v1/auth.py` | 认证接口（注册/登录/登出） |
| `api/v1/card.py` | 记忆卡片接口 |
| `api/v1/conversation.py` | 对话接口 |
| `api/v1/dev.py` | 开发者模式接口 |
| `api/v1/diary.py` | 日记 CRUD 接口 |
| `api/v1/error_handlers.py` | 全局错误处理注册 |
| `api/v1/export.py` | 数据导出接口 |
| `api/v1/feedback.py` | 反馈接口 |
| `api/v1/memory.py` | 记忆管理接口 |
| `api/v1/model_download.py` | 模型下载接口 |
| `api/v1/models.py` | 模型配置管理接口 |
| `api/v1/stats.py` | 统计接口 |
| `api/v1/tags.py` | 标签管理接口 |
| `api/v1/weekly.py` | 周记接口 |

### 4.3 domain 模块

**agents 子模块**

| 文件 | 职责 |
|------|------|
| `agents/supervisor.py` | 监督智能体（中枢：分类+技能+路由+合成） |
| `agents/empathy_agent.py` | 共情智能体（Worker） |
| `agents/retrieval_agent.py` | 检索智能体（Worker） |
| `agents/insight_agent.py` | 洞察智能体（Worker） |
| `agents/graph.py` | 多智能体图（asyncio 并发编排） |
| `agents/context_compressor.py` | 上下文压缩器 |
| `agents/intent_classifier.py` | 日记意图分类器（4 类日记意图） |
| `agents/chat_intent_classifier.py` | 对话意图分类器（6 类对话意图） |
| `agents/slot_extractor.py` | 槽位提取器 |
| `agents/entity_extractor.py` | 实体提取器 |
| `agents/query_understander.py` | 查询理解器 |
| `agents/state.py` | 多智能体状态定义 |
| `agents/types.py` | 意图类型定义 |
| `agents/prompts.py` | 提示词常量资产 |

**memory 子模块**

| 文件 | 职责 |
|------|------|
| `memory/atom.py` | 统一记忆原子（UnifiedMemoryAtom） |
| `memory/episodic.py` | 情景记忆（进程内 deque + SQLite 持久化） |
| `memory/long_term.py` | 长期记忆（用户画像） |
| `memory/working.py` | 工作记忆 |
| `memory/gate.py` | 记忆门控（四维检查） |
| `memory/types.py` | 记忆类型定义 |

**rag 子模块**

| 文件 | 职责 |
|------|------|
| `rag/retriever.py` | 混合检索器（BM25 + 向量 + 重排序） |
| `rag/collections.py` | 日记向量集合 |
| `rag/card_collections.py` | 记忆卡片向量集合 |
| `rag/base_collection.py` | Chroma 向量集合基类 |
| `rag/bm25.py` | BM25 关键词索引 |
| `rag/reranker.py` | 重排序器 |
| `rag/chunker.py` | 文本分块器 |
| `rag/types.py` | RAG 类型定义 |

**skills 子模块**

| 文件 | 职责 |
|------|------|
| `skills/base.py` | 技能基类 |
| `skills/registry.py` | 技能注册表（选择+激活） |
| `skills/crisis_detector.py` | 危机检测技能 |
| `skills/sentiment_skill.py` | 情感分析技能 |
| `skills/entity_tracker_skill.py` | 实体追踪技能 |
| `skills/memory_recall_skill.py` | 记忆回忆技能 |
| `skills/injection.py` | 技能注入 |
| `skills/skill_loader.py` | 技能加载器 |
| `skills/types.py` | 技能类型定义 |

**feedback 子模块**

| 文件 | 职责 |
|------|------|
| `feedback/prompt_tuner.py` | 提示词调优器 |
| `feedback/thompson_sampling.py` | 汤普森采样（多臂赌博机） |
| `feedback/implicit_style.py` | 隐式风格偏好提取 |
| `feedback/types.py` | 反馈类型定义 |

**knowledge 子模块**

| 文件 | 职责 |
|------|------|
| `knowledge/store.py` | 领域知识存储 |
| `knowledge/types.py` | 知识类型定义 |

### 4.4 infrastructure 模块

| 文件 | 职责 |
|------|------|
| `database.py` | SQLAlchemy 引擎/会话（SQLite+MySQL 双引擎）+ 轻量迁移 |
| `auth.py` | JWT 认证（签发/解码/OAuth2） |
| `security.py` | API Key 加密/解密（Fernet） |
| `redis_client.py` | Redis 客户端（带可用性检测） |
| `task_queue.py` | 任务队列（RQ/线程降级） |
| `entity_graph.py` | 实体关系图（Neo4j，降级 SQLite） |
| `jwt_blacklist.py` | JWT 黑名单（Redis/内存降级） |
| `session_cache.py` | 会话上下文缓存（Redis L2/内存 L1） |
| `model_config_cache.py` | 模型配置缓存（Redis/内存降级） |
| `mcp_server.py` | MCP 服务器（外部工具暴露） |
| `llm_call_tracer.py` | LLM 调用 SQLite 追踪器 |
| `agent_decision_logger.py` | Agent 决策 SQLite 日志器 |
| `skill_activation_tracer.py` | 技能激活 SQLite 追踪器 |
| `memory_repository.py` | 记忆存储 SQLite 仓库 |
| `feedback_repository.py` | 反馈存储 SQLite 仓库 |

**ORM 模型（17 个表）**

| 文件 | 对应表 |
|------|--------|
| `models/user.py` | users |
| `models/diary_entry.py` | diary_entries |
| `models/analysis.py` | analyses |
| `models/conversation.py` | conversations + chat_messages |
| `models/memory.py` | memories |
| `models/memory_card.py` | memory_cards |
| `models/tag.py` | tags |
| `models/feedback.py` | feedback |
| `models/feedback_record.py` | feedback_records |
| `models/weekly_report.py` | weekly_reports |
| `models/model_provider.py` | model_providers |
| `models/app_config.py` | app_config |
| `models/llm_call_log.py` | llm_call_logs |
| `models/pipeline_trace.py` | pipeline_traces |
| `models/agent_decision.py` | agent_decisions |
| `models/skill_activation.py` | skill_activations |

### 4.5 services 模块

| 文件 | 职责 |
|------|------|
| `container.py` | 依赖注入容器（ServiceContainer），分阶段启动 |
| `analysis_service.py` | 日记分析服务（场景一入口） |
| `conversation_ai_service.py` | 对话 AI 服务（场景二入口） |
| `diary_service.py` | 日记 CRUD（含 Chroma 向量同步） |
| `conversation_service.py` | 对话 CRUD 服务 |
| `memory_gateway.py` | 记忆网关（统一读写入口） |
| `memory_service.py` | 记忆管理服务 |
| `card_service.py` | 记忆卡片服务 |
| `card_prompt_service.py` | 卡片提示词服务 |
| `tag_service.py` | 标签服务 |
| `stats_service.py` | 统计服务 |
| `export_service.py` | 数据导出服务 |
| `weekly_service.py` | 周记生成服务 |
| `feedback_service.py` | 反馈服务 |
| `model_service.py` | 模型配置服务 |
| `model_downloader.py` | 模型下载器（HuggingFace 镜像） |
| `normalizer.py` | 内容归一化器 |
| `image_service.py` | 图片资产服务 |
| `ai/router.py` | 执行规划器（ExecutionPlanner，层级路由） |
| `ai/agent_executor.py` | Agent 执行器（ReAct 模式） |
| `ai/chain_executor.py` | 链式执行器 |
| `ai/multi_agent_executor.py` | 多智能体执行器 |
| `ai/conversation_graph.py` | 对话 LangGraph StateGraph（6 节点） |
| `ai/conversation_loop.py` | 对话循环（双路径：原生 + 文本标签） |
| `ai/graph_nodes.py` | 图节点定义 |
| `ai/input_preprocessor.py` | 输入预处理器（清洗+NFC+安全+省略补齐） |
| `ai/session_context.py` | 会话上下文管理 |
| `ai/tool_factory.py` | 工具工厂（内置+MCP 工具映射） |
| `ai/prompts.py` | AI 提示词常量 |
| `ai/utils.py` | AI 工具函数 |

### 4.6 shared 模块

| 文件 | 职责 |
|------|------|
| `errors.py` | 统一应用错误（AppError 体系） |
| `llm.py` | LLM 客户端协议与工具函数 |
| `llm_factory.py` | LLM 工厂（层级客户端创建） |
| `tracing.py` | 追踪接口与记录类型（可观测性端口） |
| `tracing_llm.py` | 追踪 LLM 客户端装饰器 |
| `pipeline_trace.py` | 管道追踪（开发者模式可观测性） |
| `trace_event_bus.py` | 追踪事件总线 |
| `trace_persistence.py` | 追踪持久化 |
| `crisis_guard.py` | 危机守卫（安全检测） |
| `emotion_estimator.py` | 情感评估器 |
| `embeddings.py` | 嵌入函数构建器 |
| `context.py` | 用户上下文（UserContext） |
| `token_utils.py` | Token 计算工具 |
| `tool_protocol.py` | 工具协议定义 |
| `chromadb_telemetry_compat.py` | ChromaDB 遥测兼容补丁 |

### 4.7 workers 模块

| 文件 | 职责 |
|------|------|
| `workers/worker.py` | RQ Worker 入口点 |

---

## 5. 调用关系

### 5.1 请求流转链路

```
HTTP 请求
  ↓
api/v1/*.py          路由端点，接收请求
  ↓
api/deps.py          依赖注入：获取 ServiceContainer、DB 会话、当前用户
  ↓
services/*.py        业务编排：调用领域服务或基础设施
  ↓
domain/*.py          领域逻辑：智能体编排、记忆读写、RAG 检索
  ↓
infrastructure/*.py  持久化：数据库操作、外部服务调用
  ↓
api/mappers.py       响应映射：ORM 行 → Schema
  ↓
HTTP 响应
```

### 5.2 依赖注入关系（ServiceContainer）

`ServiceContainer` 是整个后端的核心依赖管理器，采用**分阶段启动**策略：

```
ServiceContainer
│
├── create_core()  ← 核心阶段（快速启动，支持 /ready 和日记 CRUD）
│   ├── Settings（配置加载）
│   ├── 目录创建（data_dir / chroma_persist_dir / models_dir / backups_dir / logs_dir）
│   ├── Engine + SessionFactory（SQLAlchemy，SQLite/MySQL）
│   ├── init_db（建表 + 轻量迁移）
│   ├── LLMFactory（LLM 客户端工厂）
│   ├── SqliteLLMCallTracer（LLM 调用追踪）
│   ├── SqliteAgentDecisionLogger（Agent 决策日志）
│   ├── SqliteStylePreferenceStore（风格偏好存储）
│   └── SqliteSkillActivationTracer（技能激活追踪）
│
├── ensure_ai_stack()  ← AI 阶段（懒加载，首次 AI 调用时触发）
│   ├── DiaryCollectionManager（日记向量集合，ChromaDB）
│   ├── CardCollectionManager（卡片向量集合，ChromaDB）
│   ├── DomainKnowledgeStore（领域知识存储）
│   ├── BM25Index（BM25 关键词索引）
│   ├── Reranker（重排序器，可选，降级为 None）
│   ├── HybridRetriever（混合检索器）
│   ├── EpisodicMemory（情景记忆）
│   ├── LongTermMemory（长期记忆）
│   └── WorkingMemory（工作记忆）
│
├── build_multi_agent_graph()  ← 多智能体图（场景一）
│   ├── SupervisorAgent（中枢：IntentClassifier + SkillRegistry + LLM）
│   ├── EmpathyAgent（共情 Worker，medium 层级 LLM）
│   ├── RetrievalAgent（检索 Worker）
│   ├── InsightAgent（洞察 Worker，heavy 层级 LLM）
│   ├── ContextCompressor（上下文压缩器）
│   └── PromptTuner（提示词调优器 + ThompsonSampling）
│
├── build_execution_planner()  ← 执行规划器（场景一核心）
│   └── ExecutionPlanner（llm_by_tier + multi_agent_graph + retriever + 3层memory）
│
├── get_chat_intent_classifier()  ← 对话意图分类器（场景二）
├── get_chat_skill_registry()     ← 对话技能注册表（场景二）
└── get_conversation_graph()      ← 对话 LangGraph 状态图（场景二）
```

### 5.3 两大 AI 场景调用链

**场景一：日记分析**

```
POST /api/v1/diaries/{id}/analyze
  ↓
api/v1/analysis.py → deps.get_container()
  ↓
analysis_service.trigger_analysis()
  ├── diary_service 查找日记
  ├── ExecutionPlanner.execute()
  │   ├── 输入预处理（清洗/NFC/安全/省略补齐）
  │   ├── MultiAgentGraph.run()
  │   │   ├── Supervisor：意图分类 → 技能选择 → 路由决策
  │   │   ├── Empathy/Retrieval/Insight 并发执行
  │   │   ├── ContextCompressor 压缩上下文
  │   │   └── PromptTuner 风格调优
  │   ├── 记忆网关：写入情景记忆 → 晋升长期画像
  │   └── 管道追踪：记录执行轨迹
  └── 持久化分析结果
```

**场景二：多轮对话**

```
POST /api/v1/conversations/{id}/messages
  ↓
api/v1/conversation.py → deps.get_container()
  ↓
conversation_ai_service.generate_reply()
  ├── ChatIntentClassifier 意图分类
  ├── ConversationLoop.execute()
  │   ├── 输入预处理
  │   ├── ConversationGraph（LangGraph 6 节点）
  │   │   ├── 查询理解（共指消解 + 声明式改写）
  │   │   ├── 记忆回忆（RAG 检索 + 情景记忆）
  │   │   ├── 回复生成（层级 LLM 路由）
  │   │   └── 危机检测（安全拦截）
  │   └── 上下文压缩（滑窗 + 层级摘要 + 情景溢出）
  ├── 记忆网关：写入情景记忆（source='chat'）
  └── 管道追踪
```

### 5.4 记忆系统数据流

```
日记/对话输入
  ↓
MemoryGateway（统一入口）
  ├── MemoryGate 四维门控
  │   ├── 内容有效性检查
  │   ├── 危机污染检查
  │   ├── 情感显著性检查
  │   └── 去重检查
  ↓
EpisodicMemory（情景记忆）
  ├── 进程内 deque（衰减过滤）
  └── SQLite 持久化
  ↓
LongTermMemory（长期记忆晋升）
  ├── 连续 N 天出现同一标签 → 晋升为用户画像
  └── 标签匹配（非原始文本匹配）
```

---

## 6. 中间件角色与降级策略

所有外部基础设施均实现**优雅降级**，确保核心功能在部分服务不可用时仍可运行。

| 中间件 | 主要用途 | 降级方案 |
|--------|----------|----------|
| MySQL | 生产数据库 | 开发环境使用 SQLite，无需 MySQL |
| Redis | JWT 黑名单 / 会话缓存 / 模型配置缓存 | 降级为进程内字典（`jwt_blacklist.py` / `session_cache.py` / `model_config_cache.py`） |
| Neo4j | 实体关系图 | 降级为 SQLite 存储（`entity_graph.py`） |
| RQ | 异步任务队列（实体提取等） | 降级为线程池同步执行（`task_queue.py`） |
| LangGraph | 对话状态图 | 不可用时降级为原生对话循环（`conversation_loop.py` 双路径） |
| ChromaDB | 向量语义检索 | 基础功能不受影响，AI 检索能力降级 |
| 重排序模型 | RAG 结果重排序 | 加载失败时降级为无重排序，使用 RRF 融合顺序 |
| LLM 服务 | AI 生成 | 不可用时返回预设错误响应，非 AI 功能正常 |

---

## 7. 配置项说明

核心配置定义于 `config.py`，通过环境变量或 `.env` 文件加载：

| 配置组 | 关键配置项 | 说明 |
|--------|-----------|------|
| 应用 | `APP_ENV` | 运行环境（development/test/production） |
| 路径 | `DATA_DIR` | 数据根目录（数据库、向量库、模型等） |
| 数据库 | `DATABASE_URL` | 数据库连接（为空则使用 SQLite） |
| LLM | `LLM_MODEL` / `LLM_API_BASE` / `LLM_API_KEY` | LLM 模型与 API 配置 |
| 安全 | `JWT_SECRET` / `MODEL_KEY_SECRET` | JWT 签名密钥 / API Key 加密密钥 |
| Redis | `REDIS_URL` | Redis 连接（可选） |
| Neo4j | `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 连接（可选） |
| CORS | `CORS_ORIGINS` | 额外允许的跨域来源 |

---

## 8. 可观测性体系

后端内置四层可观测性追踪，均基于 SQLite 持久化，可通过开发者模式界面查看：

| 追踪类型 | 实现文件 | 记录内容 |
|----------|----------|----------|
| LLM 调用追踪 | `llm_call_tracer.py` | 每次 LLM 调用的模型、Token 用量、耗时、输入/输出 |
| Agent 决策追踪 | `agent_decision_logger.py` | Supervisor 的意图分类、技能选择、路由决策 |
| 技能激活追踪 | `skill_activation_tracer.py` | 各技能的激活时间、输入、输出 |
| 管道追踪 | `pipeline_trace.py` | 完整 AI 管道的分阶段执行轨迹（开发者模式可视化） |

追踪数据通过 `trace_event_bus.py` 事件总线实时推送，`trace_persistence.py` 负责持久化，前端 DevScene 可实时展示数据链路可视化。
