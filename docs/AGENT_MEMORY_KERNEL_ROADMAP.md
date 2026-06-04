# Agent Memory Kernel 面试导向收敛方案

这份文档的目的不是继续加功能，而是给后续修改立边界：所有改动都服务于把项目呈现成一个清晰、可信、可评测的本地 Agent Memory Infrastructure 项目，面向字节跳动 AI Agent Memory、AI Agent Infra、RAG/知识库后端、搜索检索工程等相关岗位。

## 北极星

`second brain` 的核心不再是一个泛化笔记工具，而是：

> 本地优先的 Agent Memory Kernel：保存用户拥有的原始证据，把经过审查的内容沉淀成长期记忆，并通过有预算、有引用、有权限边界、可评测的 ContextPack 提供给外部 agent 使用。

这里的 `Kernel` 指“核心引擎/内核”，不是操作系统内核。它强调这个项目的主价值在后端记忆生命周期、检索、权限和评测，而不是前端画布或功能页面。对外展示时可以说 `Agent Memory Core`，对工程文档和模块边界继续使用 `Agent Memory Kernel`。

判断任何新增、重构或删除时只问一个问题：

> 这件事是否让 agent 记忆更可靠、更可审计、更好检索、更容易向面试官解释？

如果答案是否定的，默认降级、隐藏、延后或删除。

## 面试官应看到什么

项目最终要让面试官在 3 分钟内看懂这条链路：

1. 用户或 agent 产生原始证据，系统保存为 durable SourceItem。
2. AI 或 agent 只能提出 MemoryProposal，不能直接写长期记忆。
3. 用户在 Review Gate 接受、拒绝、分流、失效或清理证据。
4. 被接受的内容进入长期记忆，并保留 MemoryDecision 和 ProvenanceEvent。
5. 外部 agent 通过 Agent Protocol 读取受限 ContextPack，而不是读取全库。
6. Retrieval/Context 质量通过固定 eval 和 scale benchmark 验证。

这个项目要证明的能力是：记忆生命周期治理、检索与上下文编排、隐私/权限边界、评测体系、本地产品可靠性。不是证明“页面很多”。

## 范围边界

### 稳定核心

- Source Vault：原始证据不可被摘要替代，支持导出、清理和权限策略。
- Review Gate：长期记忆写入必须经过待审候选和用户决策。
- Semantic Memory：正式 KnowledgeItem、规则、流程经验、知识页和 profile facts。
- ContextPack：按 query、scope、capability、budget、citation 输出给 agent。
- Agent Protocol：HTTP/CLI/MCP 都通过同一服务层，不暴露直接长期记忆写入。
- Provenance Ledger：记录 agent 读写、审查决策、证据流转。
- Evaluation Harness：用可复现实验说明检索、隐私、handoff、lifecycle 和延迟。
- Agent Usefulness Evaluation：用 baseline 对比证明外部 agent 接入后能更好接手任务、降低重复工作和上下文噪音。

### 可替换能力

- 检索算法：FTS、local sparse vector、embedding、ANN、rerank 都只是 provider。
- Context 组合策略：预算分配、去重、source diversity、trace 都可替换。
- 前端可视化：画布、搜索网络、统计卡片都只是展示壳。
- Agent 安装器：Codex、Claude Code、OpenCLI 入口只是协议适配。

### 明确非目标

- 不做通用笔记软件、社交知识库、团队协同 SaaS。
- 不做生产级多租户、高可用、云同步和权限后台。
- 不做全库知识图谱产品；当前搜索网络只作为搜索结果解释。
- 不做前端任务管理台；task state 是 agent 协议内部状态。
- 不做自动 Dreaming 直接写长期记忆；离线整理只能产出待审 proposal。
- 不把 deterministic local vector 宣称为真实 semantic embedding 或 SOTA。
- 不用更多页面弥补核心链路，面试展示只保留一条主路径。

## 外部设计借鉴边界

这些项目和文档只作为设计参照，不作为功能清单。只有能自然融入当前 durable records、Review Gate、ContextPack 和 eval harness 的部分才允许进入实施计划。

| 参照对象 | 可借鉴 | 不照搬 |
| --- | --- | --- |
| Anthropic Managed Agents Memory Stores | store 有 owner、description、instructions、read-only/read-write、version/audit/redact；多个 store 按 user/team/project/reference 拆分 | 不做 Claude sandbox 挂载，不开放 agent 直接写长期记忆 |
| Anthropic Dreams | 离线 consolidation 不修改输入，输出独立结果，可 review/discard | 不做自动 Dreaming 直接落库，不把 research preview 当近期主线 |
| LangGraph Memory | 明确 short-term/thread state 与 long-term store；把长期记忆分 semantic、episodic、procedural；支持 hot-path 和 background 写入权衡 | 不引入 LangGraph 运行时，不把项目改成 graph workflow 框架 |
| Letta / MemGPT | 区分 always-in-context core memory 与 on-demand archival memory；给记忆块 description 和大小边界 | 不让 agent 自主改核心长期记忆；不做复杂多 agent 状态平台 |
| Mem0 | user/session/run/org 分层；add/search/update/delete 的简单 API；metadata、filters、rerank、graph toggle 都可测量 | 不接入外部 MaaS，不直接上 graph backend 或托管 reranker |
| Zep / Graphiti | temporal fact、invalid_at、episode/entity/edge 分离、Context Block 和事实失效 | 不做完整 temporal graph DB；只保留 profile facts、relations、conflicts 的轻量本地版本 |

### 允许吸收的 4 个设计

1. Store Manifest
   给现有 store registry 增加面向 agent 的 manifest：`name`、`purpose`、`owner`、`visibility`、`access`、`lifecycle`、`instructions`。先作为协议返回和导出元数据，不急着新增大表。

2. Memory Version 和 Redaction
   在长期记忆被接受、更新、失效、清理时保留版本和审计入口。当前已有 `MemoryDecision` 和 `ProvenanceEvent`，后续只补可回看/可恢复的 revision 视图，不做复杂分支历史。

3. Context Selection Trace
   ContextPack 不只返回内容，还返回选中、过滤、截断、权限拒绝、去重的原因。这和现有 `warnings`、`citationRefs`、`decisionRefs` 能自然融合。

4. Background Consolidation as Proposal
   借鉴 Dreaming 的离线整理，但输出只能是 `MemoryProposal` 或独立 preview，不直接改 `KnowledgeItem`、`MemoryFact` 或原始证据。

### 暂不吸收的设计

- 完整图数据库、Neo4j/FalkorDB/Graphiti 接入。
- 多 agent orchestration 平台。
- 云端 memory store 挂载和文件系统同步。
- 自动改 prompt 或自动改系统规则。
- 公开 benchmark 适配之前的大规模排行榜叙事。

## 保留、收缩、删除

| 类别 | 处理 | 原因 |
| --- | --- | --- |
| `SourceItem`、`KnowledgeItem`、`MemoryProposal`、`MemoryDecision`、`ProvenanceEvent` | 保留为核心资产 | 这是面试叙事的 durable memory lifecycle |
| `ContextPack`、`MemoryContextComposer`、`Agent Protocol` | 保留并加深 | 对齐 agent memory / RAG infra 岗位 |
| `RetrievalEngine`、`fusion`、`rerank`、`vector` | 重设计内部边界 | 当前可用，但 provider/fusion/rerank 叙事还不够清楚 |
| `evals/` | 保留并扩展 | 面试官最容易认可的证据层 |
| Capture Board | 降级为 Capture Inbox | 它只是收集证据的入口，不是主产品 |
| Weekly 维度和卡片画布 | UI 上保留，文档中降权 | 避免项目看起来像日程/白板工具 |
| Search Knowledge Network | 改口径为 Search Explanation | 不讲全局知识图谱，只讲局部结果解释 |
| Reflections/Suggestions | 收缩到 Review Gate 的候选整理 | 不单独作为大功能宣传 |
| Profile Temporal Graph | 保留后端能力，前端低调展示 | 适合讲治理，不适合喧宾夺主 |
| 新增 Dreaming | 暂缓 | 只在路线图里作为离线 consolidation，不进近期实现 |
| 新增更多 dashboard | 禁止 | 会稀释 Agent Memory Kernel 主线 |

## 目标产品表面

后续 README、演示和 UI 都按三个入口讲：

1. Capture Inbox
   保存文本、链接、图片和 agent evidence。它回答“证据从哪里来”。

2. Search & Context Lab
   搜索长期记忆，查看命中原因、引用、ContextPack 预算和过滤说明。它回答“agent 为什么读到这些”。

3. Review Gate
   审查待审记忆、证据权限、事实失效和冲突。它回答“长期记忆为什么可信”。

CLI、MCP 和 HTTP agent protocol 不作为第四个用户页面，而是作为外部 agent 的接入层。

## 最优改进方向

近期最值得做的是 Retrieval & Context Quality Redesign，而不是新增功能。

原因：

- 它正中 AI Agent Memory / RAG / 搜索检索岗位。
- 它能提高项目技术含金量，不会让 UI 更乱。
- 它可以被 eval 量化，面试时有数字和 case。
- 它能自然连接隐私过滤、证据引用、ContextPack 预算和 agent protocol。

评估口径见 `docs/AGENT_USEFULNESS_EVALUATION.md`：它专门回答“外部 agent 接入后是否真的有用，而不是花瓶 demo”。

## 实施路线

### Phase 0：叙事冻结和文档收敛

目标：先把项目讲清楚，防止后续边改边跑偏。

改动：

- README 首段增加 Agent Memory Kernel 定位。
- README 的“使用”保留轻量产品说明，“架构约定”链接本文件。
- 架构文档引用本路线图，说明功能取舍以本文件为准。
- 不再新增临时计划文档；长期方案只维护本文件和评测协议。

验收：

- 新读者能在 1 分钟内知道项目不是白板/笔记软件，而是 agent memory infra。
- README 不把 Capture Board、搜索网络、Review Workbench 平铺成同等产品。

风险：

- 文档过度改写可能影响普通用户安装体验；安装和运行部分保持简单。

### Phase 1：Retrieval Pipeline 重设计

目标：把当前检索从“能跑的混合搜索”收束成可解释、可替换、可评测的 pipeline。

建议模块：

- `server/app/retrieval/providers.py`
  定义 `CandidateProvider`、`RetrievalCandidate`、`QueryPlan`。
- `server/app/retrieval/lexical.py`
  承接 SQLite FTS 和字段/关键词匹配。
- `server/app/retrieval/sparse.py`
  将当前 `LocalVectorSearch` 改名或包裹为 `LocalSparseVectorProvider`。
- `server/app/retrieval/fusion.py`
  保留 RRF，增加去重、source diversity 和 provider trace。
- `server/app/retrieval/rerank.py`
  显式使用 lexical score、sparse score、citation/evidence、knowledge type、recency、scope quality。
- `server/app/retrieval/engine.py`
  只负责调度 provider、fusion、rerank 和输出结果。

重要取舍：

- 保留无外部依赖的 local sparse recall，作为本地默认能力。
- 预留 embedding provider 接口，但不在这一阶段接云 embedding。
- 不把 local sparse recall 叫 semantic embedding。
- 搜索结果返回 `trace` 或 `reason`，让 ContextPack 和 UI 能解释命中原因。

验收：

- 现有 `server/tests/test_retrieval_engine.py` 通过。
- 增加 provider/fusion/rerank 单测。
- `python evals/run_memory_eval.py` 中 retrieval ablation 仍能输出 lexical/sparse/hybrid 对比。
- 负例 query 不应被高相似泛化污染。

面试讲法：

> 我把检索拆成 candidate providers、RRF fusion 和 lightweight rerank，默认本地 sparse recall 无需外部服务，但接口可以替换成 embedding/ANN；所有改动都通过 ablation 和 privacy cases 验证。

### Phase 2：ContextPack Budget Optimizer

目标：从“取 topK 塞上下文”升级为“按收益选择上下文”。

改动：

- 在 `memory_core` 增加 ContextPack selection/optimizer 层。
- 对每个 slice 计算 utility：query relevance、evidence coverage、decision confidence、freshness、source diversity、store priority。
- 对同一 source 的重复内容去重，只保留代表项和 source excerpt。
- 查询意图明显是规则/流程时，提高 rule/procedure 的预算占比。
- 查询意图明显是 task handoff 时，提高 task state/digest 的预算占比。
- 返回 `selectionTrace`：选中、过滤、截断、权限过滤原因。

验收：

- ContextPack 仍遵守 `maxChars`。
- `citationRefs` 覆盖每个关键 item。
- private/profile/task-scope 内容默认不泄露。
- eval 增加 budget pressure、duplicate source、wrong scope、rule query、handoff query case。

面试讲法：

> 我没有把检索结果直接塞进 prompt，而是做了 ContextPack 编排：预算、去重、引用、权限、store priority 和 trace 都能解释。

### Phase 3：Review Gate 和 UI 降噪

目标：让前端看起来像一个 agent memory 系统，而不是功能拼盘。

改动：

- 顶部导航命名收敛为 Capture、Search/Context、Review。
- Board 页面文案改为 Capture Inbox，不强调周视图。
- Search 页面弱化网络图，把它称为结果解释；优先展示命中原因、引用、ContextPack 入口。
- Review Workbench 首屏只突出 pending proposals、source policy、export；facts/conflicts/rules/procedures 折叠或放二级区域。
- Suggestions/Reflections 合并进 Review Gate 的候选整理口径。

不做：

- 不新增大 dashboard。
- 不新增独立 graph 页面。
- 不新增任务管理页面。

验收：

- 用户第一次打开能理解三件事：收集证据、检索上下文、审查记忆。
- `npm run test:smoke` 覆盖三个入口。
- 面试 demo 不超过 3 分钟。

### Phase 4：Evaluation Gate

目标：把“我做了系统”变成“我能证明系统可靠”。

改动：

- `evals/run_memory_eval.py` 拆成小模块，避免单文件继续膨胀。
- 增加固定 retrieval suites：
  - exact keyword
  - paraphrase / word order
  - negative query
  - private/profile/scope leak
  - duplicate source
  - stale vs fresh
  - budget pressure
- 报告明确区分：
  - `recall@K`
  - `precision@K`
  - `MRR`
  - `negativeAccuracy`
  - `privacyLeakRate`
  - `citationCoverage`
  - `p95LatencyMs`
- CI 或本地验收门槛写入 README。

验收：

- 内部 challenge 分数稳定，不追求 100%。
- 公开说明 `publicBenchmarkStatus=not_run`，避免夸大。
- scale benchmark 保留 local SQLite 口径，不宣称分布式生产 QPS。

### Phase 5：可选的 Memory Consolidation

目标：借鉴 Dreaming，但不让项目失控。

只做本地离线整理，不自动写长期记忆：

```text
recent SourceItem / TaskEvent / accepted KnowledgeItem
-> consolidation job
-> MemoryProposal candidates
-> Review Gate
-> accepted memory
```

边界：

- 不修改原始 source。
- 不直接修改 accepted memory。
- 不自动解决冲突。
- 不默认读取 private/profile 内容。
- 每个 consolidation 输出都有 evidence refs 和 confidence。

这一阶段只有在 Phase 1-4 完成后再做。

## 文件级改动清单

优先级从高到低：

| 阶段 | 文件/模块 | 动作 |
| --- | --- | --- |
| 0 | `README.md` | 收敛定位，链接本路线图 |
| 0 | `docs/SECOND_BRAIN_ARCHITECTURE.md` | 引用路线图，声明取舍边界 |
| 1 | `server/app/retrieval/*` | 拆 provider/fusion/rerank/engine |
| 1 | `server/tests/test_retrieval_engine.py` | 增加 provider 和 trace 测试 |
| 2 | `server/app/memory_core/composer.py` | 引入 ContextPack selection/optimizer |
| 2 | `server/tests/test_memory_core.py` | 增加预算、引用、权限测试 |
| 3 | `client/src/App.tsx`、`client/src/pages/*` | UI 文案和入口降噪 |
| 3 | `client/src/App.smoke.test.tsx` | 覆盖三个主入口 |
| 4 | `evals/run_memory_eval.py` | 拆分并扩展 suites |
| 4 | `docs/MEMORY_EVALUATION_PROTOCOL.md` | 更新质量门槛 |

## 删除和延后原则

可以删除：

- 阶段性计划文档、重复 README 说明、已经被路线图替代的临时说明。
- 与 Agent Memory Kernel 无关的前端入口或文案。
- 声称全局图谱、通用笔记、生产 SaaS 的表达。

先不要删除：

- 现有 capture board 数据模型和 UI。它仍是证据入口。
- Profile graph 后端模型。它是记忆治理证据。
- Task handoff 后端能力。它是跨 agent 场景的核心案例。

延后：

- Dreaming / consolidation。
- 真 embedding provider。
- pgvector、Faiss、ANN。
- Playwright E2E。
- 大规模公开 benchmark adapter。

## 面试展示脚本

推荐 demo 路线：

1. 打开项目，说明这是本地 Agent Memory Kernel。
2. Capture Inbox 粘贴一段证据或截图，生成 SourceItem。
3. 外部 agent 通过 `/api/agent/context` 请求上下文，展示 ContextPack、budget、citationRefs、warnings。
4. agent 只能创建 MemoryProposal，不能直接写长期记忆。
5. Review Gate 接受 proposal，生成 KnowledgeItem、MemoryDecision、ProvenanceEvent。
6. 搜索同一主题，展示 hybrid retrieval reason 和 source excerpt。
7. 打开 eval 报告，说明 retrieval、privacy、handoff、lifecycle 和 scale 的证据边界。

简历一句话：

> 设计并实现本地优先的 Agent Memory Kernel，支持 review-gated long-term memory、budgeted ContextPack、capability-based privacy isolation、agent protocol、provenance audit 与 deterministic eval harness；检索链路采用 lexical/local sparse recall + RRF fusion + lightweight rerank，并通过内部 challenge 评测检索、隐私、handoff 和 lifecycle 可靠性。

## 每次改动前的检查清单

- 这次改动是否强化 Agent Memory Kernel 主线？
- 是否会增加新的用户入口？如果会，能否复用现有三个入口？
- 是否会让 agent 绕过 Review Gate？
- 是否保留了 SourceItem 原始证据？
- 是否有 citation/provenance？
- 是否能被 eval 或测试覆盖？
- 是否能在面试中用一句话解释？

不满足这些条件的改动，默认不做。
