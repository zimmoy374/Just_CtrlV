# second brain 整体架构与说明

`second brain` 是一个本地优先的个人知识与记忆系统。它保存用户拥有的原始证据，把经过审查的内容沉淀成长期记忆，并通过有预算、有引用、有权限边界的 ContextPack 给用户和外部 agent 使用。

## 核心原则

- 原始证据是最重要的用户资产。
- 长期记忆必须经过审查决策写入，agent 不能静默写入、覆盖、删除或解决冲突。
- 搜索、上下文组合、索引和导出都是 durable records 之上的可替换 projection。
- agent 只能通过稳定协议读取受限上下文、读取明确引用的证据摘录、创建待审记忆。
- agent 读取个人资料、私密或敏感内容必须声明本地 `capabilityProfile`；默认 `work` 档位只允许普通工作接力。
- agent 的任务状态是协议内部状态，不是个人知识库的前端工作台。
- 新框架路径和被替代路径冲突时，只保留新框架路径。
- 跨 agent 接力以本地工作区绑定、滚动摘要和稳定协议为核心，不依赖聊天窗口里残留的上下文。
- 压缩只作用于给 agent 读取的上下文投影；原始证据、任务事件和用户输入不能被摘要替换。

## 产品表面

- Capture Board：保存文本、链接和图片卡片。
- Knowledge Workspace：搜索知识、查看搜索关联网络、读取 ContextPack。
- Review Workbench：审查待审记忆、个人事实、冲突、规则、流程经验、知识页和原始证据。
- Export：导出完整、可检查、可迁移的记忆包。

## 后端边界

FastAPI 路由按职责拆分：

- `cards`：文本、链接、图片捕获和分析任务。
- `knowledge`：搜索、context、已确认导入、导出、整理建议。
- `tasks`：外部 agent 协议内部使用的任务 session、状态、事件、checkpoint 和 handoff；它不是用户长期知识入口。
- `memory`：projection rebuild。
- `agent`：`/api/agent/*` 稳定 agent protocol。
- `review`：`/api/review/*` 用户审查权限边界。
- `system`：`/api/system/status` 本地运行状态、存储、任务、分析任务和审计概览。

核心模块：

- `knowledge_core`：source item、knowledge item、page link、retrieval。
- `memory_core`：协议对象、store registry、router、context composer、profile graph、decision、provenance。
- `memory_kernel`：memory proposal 的创建、列表、接受、拒绝。
- `tasks`：task session、event、state、checkpoint、handoff 服务；状态切换集中由 `tasks/state_machine.py` 校验，`/api/tasks/*` 和 `/api/agent/tasks/*` 都不能绕过终态保护。
- `agent_runtime`：工作区绑定、agent 入口安装器、capability profile。
- `export`：导出边界和 bundle writer。
- `indexing`：可重建的 SQLite FTS projection。

## Durable Stores

- Source Vault：`SourceItem` 保存文本、链接、图片分析、任务事件和外部导入证据。
- Semantic Knowledge：`KnowledgeItem`、`KnowledgePage`、`KnowledgePageItemLink` 保存正式知识和主题页。
- Agent Task State：`TaskSession`、`TaskState`、`TaskEvent`、`TaskCheckpoint`、`HandoffPack` 保存外部 agent 接入过程中的工作状态；它不直接构成用户长期知识。
- Task Digest：`TaskDigest` 保存较早任务事件的滚动摘要，是可重建的工作状态 projection；它只用于压缩 handoff 和 ContextPack。
- Memory Review：`MemoryProposal` 保存候选长期记忆，`MemoryDecision` 保存审查决策。
- Profile Temporal Graph：`Entity`、`MemoryFact`、`MemoryRelation`、`MemoryConflict` 保存 profile fact、relation、supersession、invalidation 和 conflict lifecycle。
- Provenance Ledger：`ProvenanceEvent` 记录记忆为什么存在、如何流转、哪些 refs 被暴露或改变。

## 写入路径

- 用户捕获内容会写入 card 和 source evidence，分析后可以形成可搜索知识。
- 用户确认过的外部导入可以直接写入 source evidence 和 semantic knowledge。
- agent task event 会追加协议内部工作状态，并同步留下 source evidence。
- 任务状态、任务事件和 checkpoint 写入前必须确认任务不是终态；终态任务只能读取、handoff 预览或归档。
- agent 可以通过 `/api/agent/proposals` 创建 pending proposal，但不能接受、拒绝、解决冲突或 purge source。
- 长期记忆只能在用户审查后通过 `MemoryRouter.accept_proposal()` 写入 durable store。
- Review Workbench 的 accept、reject、reroute、supersede、invalidate、resolve、source policy、source purge 都会写入 decision 和 provenance。

## 读取路径

- `/api/knowledge/search` 搜索经过审查的 semantic knowledge；前端会把当次搜索结果转换成局部关联网络。
- `/api/knowledge/context` 和 `/api/agent/context` 返回由多个 store slice 组合出来的 ContextPack，并执行 scope、visibility、privacy label、capability、budget、citation、decision 和 warning 控制。
- `/api/agent/source-excerpt` 只从显式 `source:` ref 返回预算化 excerpt。
- `/api/agent` 和 `/api/agent/instructions` 是外部 agent 的入口说明；agent 应先读它，再读 `/api/agent/tools`。
- `/api/agent/capabilities` 返回本地 capability profile。默认 `work` 不读私密内容；`profile`、`private`、`sensitive`、`trusted` 逐步扩大读取范围，但都不能直接写正式长期记忆。
- `second_brain.py resume` 和 MCP `resume_work` 是 agent 切换时的默认恢复入口，优先读取当前工作区绑定的活跃任务。
- `second_brain.py doctor` 和 `/api/system/status` 是本地诊断入口，用来检查数据库、工作区绑定、活跃任务、待处理分析任务、待审记忆和 provenance。
- `/api/review/workbench` 只聚合 proposals、facts、conflicts、rules、procedures、pages 和 source evidence；它不返回 task capsule 或 agent access 列表。
- agent 读取/写入审计保存在 `ProvenanceEvent`，通过 `/api/system/status` 的近期概览和导出包查看，不混入记忆审查台。
- `/api/knowledge/export` 生成可人工检查的完整导出包。

## 跨 Agent 接力

项目根目录的 `AGENTS.md` 是通用 agent 入口。`second_brain.py install-agent` 会为 Codex、Claude Code 和 OpenCLI 风格工具生成或更新对应入口，但只维护 second brain 标记块，不覆盖用户自己的规则。

`.second-brain/workspace.json` 是本地工作区接力指针，保存 workspace id、活跃任务 id 和最近接力时间。它不是长期记忆资产，不进入导出包，也不提交到版本库。

Handoff 默认读取：

- 当前任务状态。
- `TaskDigest` 里的较早事件滚动摘要。
- 最近少量任务事件。
- checkpoint、event、source refs。

agent 需要更多细节时必须按 ref 读取，不允许全量读取任务历史或数据库。

任务状态机：

- 活跃态：`open`、`paused`、`handoff_ready`、`waiting_user`。
- 收尾态：`closing_review`。
- 终态：`closed`、`archived`、`expired`。
- 终态任务不能再被任何 task 写入 API 写入事件、状态或 checkpoint；需要继续工作时创建新任务，而不是复活已结束任务。

当前架构判断：

- 合理保留：source evidence、semantic knowledge、review gate、ContextPack、agent task state、provenance、export。
- 可替换：检索算法、上下文组合策略、前端搜索网络、agent 安装器外壳。
- 不再保留：全库知识图谱页、前端任务工作台、旧框架文档、审查台里的 task capsule/agent read 面板。

## 导出与重建边界

导出分三层：

- durable records：sources、items、pages、tasks、proposals、decisions、profile graph、conflicts、handoffs、provenance。
- store views：rules、procedures 和 task digests；它们由 durable records 生成或承载，不替代原始记录。
- derived projections：SQLite FTS 等索引，不作为记忆导出，可从 durable records 重建。

`provenance.jsonl` 带 hash chain，用于本地审计检查，不是 agent 共识机制。

## 验证

架构边界、路由、store、export 或 review 流程改动后，至少运行：

```powershell
python -m pytest server/tests
cd client
npm run lint
npm run build
```

如果改动了前端交互界面，还需要启动应用并在浏览器里检查对应页面。
