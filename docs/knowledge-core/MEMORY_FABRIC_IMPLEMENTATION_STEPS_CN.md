# Memory Fabric 中文实施步骤

本文承接 `MEMORY_FABRIC_PLAN.md`，把路线图拆成可执行、可验收的工程步骤。本项目是全新的第一版，没有线上历史用户、历史 API 契约或历史数据迁移负担；实现应直接采用目标 Memory Fabric 协议。

第一版原则：不要为了不存在的历史版本设计中间层、双路径、字段镜像或回填流程。除非真的接入第三方协议，否则文档和代码都应使用“store / protocol / router / composer / projection”等第一版术语。

如果后续执行建议、代码注释或实现方案与本文冲突，以本文为准；不要额外增加守门测试或流程判断来替代这个架构约定。

## 评估结论

`MEMORY_FABRIC_PLAN.md` 的方向是正确的：它没有急着引入 Graphiti、向量库或新图数据库，而是先要求稳定的 memory protocol，再让不同 store 在协议后面演进。这和当前代码状态匹配。

当前项目已经具备四块第一版基础：

- Source Vault 雏形：`SourceItem` 已经保存原始证据，任务事件也会同步写入 source。
- Semantic Knowledge 雏形：`KnowledgeItem`、`KnowledgePage`、`KnowledgePageItemLink` 已经承担正式知识和主题页。
- Task Memory 雏形：`TaskSession`、`TaskEvent`、`TaskState`、`TaskCheckpoint`、`HandoffPack` 已经形成任务胶囊。
- ContextPack 雏形：`/api/knowledge/context` 已经做了预算、citation refs 和 source excerpt 限制。

主要缺口也清楚：

- 还没有统一的 `MemoryRef`、`MemorySlice`、`MemoryStore` 协议层。
- `MemoryProposal.accept` 仍然直接写入 `KnowledgeItem` 或 `KnowledgePage`，还没有经过 router。
- `ContextPack` 直接调用 retrieval/page/source 逻辑，还不是由多个 store 返回 slice 后统一组合。
- 还没有 profile temporal graph 相关模型，不应在 Step 1 提前建表。
- 还没有元记忆记录解释“为什么这条记忆被保留、拒绝、失效、替代或暴露给 agent”。
- provenance 目前更多体现在 export，不是明确的 append-only decision ledger。
- 隐私、scope、visibility、agent capability 还没有成为协议字段。
- 多 agent 产生矛盾记忆时，未来需要明确 conflict / supersession / invalidation 的处理流程。

因此 Step 1 的正确切入点是“建立协议骨架和只读 store”，而不是“先加 profile graph 等新记忆类型”。

## Step 0.5: 架构补强，明确非目标和约束

### 目标

在写协议代码前，把多 agent 共享记忆最容易失控的部分提前定清楚：元记忆、provenance ledger、冲突处理、隐私权限、短期长期分层、一致性策略。

### 核心结论

- 不做“所有 agent 共同维护一条去中心化记忆链”作为主架构。
- 可以借鉴区块链的 append-only、hash、tamper-evident export 思想，但用户是 trust root，不是 agent 共识。
- 共享记忆不是共享数据库，而是通过 `MemoryRef`、`MemorySlice`、`ContextPack`、`MemoryProposal` 等协议受控共享。
- agent 可以记录任务事件、创建 checkpoint、生成 proposal，但不能绕过 review gate 写长期记忆。
- 每条长期记忆都应该能回答“为什么值得记、证据是什么、谁确认、谁能看、什么时候失效、被谁替代”。

### 需要写进主方案的概念

- Meta Memory / `MemoryDecisionRecord`
  记录 proposal 创建、接受、拒绝、冲突解决、事实失效、事实替代、上下文暴露、隐私变更等决策。

- Provenance Ledger / `ProvenanceEvent`
  本地优先、用户拥有、可导出、可选 hash-linked 的审计链。它不是区块链共识层。

- Privacy And Access Policy
  给协议预留 `scope`、`visibility`、`privacy_labels`、`capability_requirements`、`redaction_policy`、`retention_policy`。

- Conflict Lifecycle
  当两个 agent 或两段证据产生矛盾时，不静默覆盖，进入 `MemoryConflict`、`superseded_by`、`invalid_at` 或 scoped alternative。

- Consistency Policy
  Source Vault 和 review decision 要强持久；Task handoff 可以 stale 但必须标记；retrieval projection 可以最终一致并可重建。

### 验收标准

- `MEMORY_FABRIC_PLAN.md` 明确说明 Memory Fabric 不是 decentralized blockchain。
- 主方案中有元记忆、provenance ledger、冲突、隐私权限、一致性策略的章节。
- 后续 Step 1 的协议字段能承载这些未来概念，即使当前不落库。
- 面试或设计评审时能清楚解释：为什么不把所有记忆放进一个共享数据库，为什么不让 agent 共同决定真相。

### 当前落实状态

- 已落实到 `MEMORY_FABRIC_PLAN.md`：主方案明确用户是 trust root，append-only provenance 是本地审计账本，不是 decentralized agent consensus。
- 已落实到 `MEMORY_FABRIC_PLAN.md`：Meta Memory、Privacy And Access Policy、Conflict Lifecycle、Consistency And Availability Policy 都已有独立章节。
- Step 1 的协议对象必须保留这些未来字段；第一版可以直接让入口走协议层，但不提前创建 profile graph 表。

## Step 1: 第一版协议骨架

### 目标

引入 Memory Fabric 的稳定内部协议，让语义知识、任务记忆和上下文构建都从第一版开始围绕统一接口组织，同时为元记忆、隐私权限、冲突和 provenance 预留字段。

### 非目标

- 不新增 `Entity`、`MemoryFact`、`MemoryRelation` 等 profile graph 表。
- 不提前实现完整 profile graph 的 conflict/supersession 行为。
- 不引入外部 graph/vector 依赖。

### 建议文件

```text
server/app/memory_core/
server/app/memory_core/__init__.py
server/app/memory_core/protocol.py
server/app/memory_core/stores.py
server/app/memory_core/router.py
server/app/memory_core/composer.py
```

### 执行内容

1. 新建 `memory_core.protocol`。
   - 定义 `MemoryRef`，支持 `source:`、`item:`、`page:`、`task:`、`task-event:`、`checkpoint:`、`handoff:`、`proposal:` 等当前已经存在的 ref 前缀。
   - 定义 `MemoryEpisodeInput`，用于描述进入 memory system 的原始事件，但 Step 1 只作为类型，不接入写链路。
   - 定义 `MemorySlice`，作为所有 store 返回给 composer 的统一只读结果，并预留 `scope`、`visibility`、`privacy_labels`、`evidence_refs`、`decision_ref`、`conflict_refs`、`staleness`。
   - 定义 `MemoryStore` Protocol，至少包含 `retrieve()`、`get()`、`export()`、`rebuild_projection()` 的概念签名；暂时允许部分方法返回空或 `NotImplemented`。
   - 定义轻量的 `MemoryDecisionRecord` / `ProvenanceEvent` 类型，只作为协议对象，不落库。

2. 新建 `memory_core.stores`。
   - 实现 `SemanticKnowledgeStore`，内部使用 `RetrievalEngine`、`KnowledgeItem`、`KnowledgePage`、`SourceItem`，输出 `MemorySlice`。
   - 实现 `TaskMemoryStore`，读取 `TaskSession`、`TaskState`、`TaskEvent`、`TaskCheckpoint`、`HandoffPack`，先支持按 task scope 返回状态和最近事件。
   - store 只负责把 durable memory 投影成 `MemorySlice`，排序、预算和摘录仍交给 composer。

3. 新建 `memory_core.router`。
   - 定义 `MemoryRouter`，保存 store registry。
   - Step 1 只提供只读注册和查找能力，例如 `get_store()`、`retrieve()`。

4. 新建 `memory_core.composer`。
   - 定义 composer 的入口和排序原则，为 Step 3 的多 store composition 做准备。
   - `/api/knowledge/context` 从第一版开始通过 `MemoryContextComposer` 进入上下文构建。

5. 增加单元测试。
   - 验证 `MemoryRef` 可以解析和格式化当前 ref。
   - 验证 `SemanticKnowledgeStore.retrieve()` 对知识项返回 `MemorySlice`，并保留 citation ref。
   - 验证空 query 或无命中时返回空 slice，不抛异常。
   - 验证 context/search/proposal/task/export 流程仍通过。

6. 在代码中直接采用第一版入口。
   - 测试中直接实例化新 store。
   - context 路由通过 `MemoryContextComposer`。
   - 所有新类型优先使用 Pydantic/dataclass/Protocol；durable proposal/decision/provenance 进入 SQLModel。

### 验收标准

- `server/app/memory_core/` 存在，并包含协议、store、router、composer 的最小实现。
- `MemoryRef` 能表达当前所有已经暴露给 agent/context/export 的 ref 类型。
- `MemorySlice` 能表达 evidence、decision、privacy、conflict、staleness 等未来字段。
- `SemanticKnowledgeStore` 能把检索结果转换为 `MemorySlice`。
- `TaskMemoryStore` 能在 task scope 下返回任务状态或任务事件 slice。
- `/api/knowledge/context` 入口走 `MemoryContextComposer`。
- `MemoryProposal` 第一版就包含 routing/review 字段。
- 测试通过，并新增覆盖协议和 store 的测试。
- 新协议文档或类型注释明确：这些字段是为了未来 Meta Memory、Conflict、Privacy 和 Provenance 服务，不代表 Step 1 已经实现完整行为。

### 推荐测试命令

```powershell
pytest
```

如本地环境只允许后端测试，可先运行：

```powershell
pytest server/tests
```

### 风险与处理

- 风险：store 重复 context/retrieval 逻辑，后续难以维护。
  处理：store 只负责返回 `MemorySlice`，排序、预算、摘录和 redaction 属于 composer。

- 风险：把 proposal routing 也塞进 Step 1。
  处理：Step 1 建协议和只读 store，Step 2 再实现 `MemoryRouter.accept_proposal()`。

## Step 2: 通用候选记忆路由

### Step 1 后的当前基线

- 已有 `server/app/memory_core/protocol.py`，包含 `MemoryRef`、`MemoryQuery`、`MemoryEpisodeInput`、`MemorySlice`、`MemoryDecisionRecord`、`ProvenanceEvent` 和 `MemoryStore` Protocol。
- 已有 `SemanticKnowledgeStore` 和 `TaskMemoryStore` 只读 store，可以把 `KnowledgeItem` / task capsule 转成 `MemorySlice`。
- 已有 `MemoryRouter` store registry。
- `/api/knowledge/context` 已通过 `MemoryContextComposer` 进入上下文构建。
- 新增测试覆盖协议解析、semantic slice、task slice、router registry；后端测试通过。

### 目标

让 `MemoryProposal` 从第一版开始由 `MemoryRouter` 按 `target_store` 分流，并留下可导出的 decision / provenance 记录。

### 非目标

- 不新增 profile temporal graph 的 `Entity`、`MemoryFact`、`MemoryRelation`、`MemoryConflict` 表。
- 不引入外部 graph/vector/reranker 依赖。
- 不让 agent 绕过 review gate 直接写长期记忆。

### 执行内容

1. 扩展协议常量。
   - 在 `memory_core.protocol` 或相邻模块中明确 `target_store` 枚举：`semantic_knowledge`、`rule_preference`、`procedure_lesson`。
   - 明确 proposal type 到默认 store 的映射：
     - `page_update` -> `semantic_knowledge`
     - `technical_decision`、`environment_fact` -> `semantic_knowledge`
     - `user_preference`、`project_rule` -> `rule_preference`
     - `lesson`、`pitfall`、`workflow_pattern` -> `procedure_lesson`
   - 未知 `target_store` 必须拒绝，不允许静默降级。

2. 增加模型字段和表。
   - 第一版 schema 直接包含这些字段，不保留旧 proposal schema。
   - `MemoryProposal` 包含：
     - `target_store`
     - `structured_payload_json`
     - `scope`
     - `confidence`
     - `review_note`
     - `decision_ref`
   - `target_store` 默认按 proposal `type` 推断；未知 `target_store` 必须拒绝。

3. 增加最小 durable decision / provenance 记录。
   - 新增 `MemoryDecision` / `ProvenanceEvent` SQLModel，或等价的 append-only durable 表。
   - 首批 decision type：
     - `proposal_created`
     - `proposal_accepted`
     - `proposal_dismissed`
     - `proposal_routed`
   - 首批 provenance event：
     - `proposal_for_task`
     - `proposal_created_source`
     - `accepted_proposal_created_item`
     - `accepted_proposal_created_page`
     - `proposal_dismissed`
   - 每条记录都要有 `target_ref` 或 `from_ref` / `to_ref`、`actor`、`reason`、`evidence_refs`、`created_at`。

4. 实现 `MemoryRouter.accept_proposal()`。
   - 接收当前 `MemoryProposal`，解析或推断 `target_store`。
   - 按 store 分流：
     - `semantic_knowledge`：写入 `KnowledgeItem` 或 `KnowledgePage`。
     - `rule_preference`：Step 2 先落到 `KnowledgeItem`，但 `knowledge_type`、keywords 或 metadata 必须标出 rule/preference store。
     - `procedure_lesson`：Step 2 先落到 `KnowledgeItem`，但 `knowledge_type`、keywords 或 metadata 必须标出 procedure/lesson store。
   - 写入成功后回填 `source_item_id`、`knowledge_item_id` 或 `page_id`，并设置 `decision_ref`。
   - 对未知 store、非 pending proposal、缺少必要 body/title 的 proposal 给出明确错误，不产生长期写入。

5. 改造 proposal 服务。
   - `create_memory_proposal()` 接受 routing/review 参数，并在创建时写入 `proposal_created` decision/provenance。
   - `accept_memory_proposal()` 改为调用 `MemoryRouter.accept_proposal()`。
   - `dismiss_memory_proposal()` 写入 decision / provenance。
   - `MemoryProposalResponse` 输出 routing/review/decision 字段。

6. 更新 export。
   - `memory_proposals.jsonl` 导出 routing/review 字段。
   - 新增 `memory_decisions.jsonl`。
   - `provenance.jsonl` 同时包含 durable provenance events 和导出推导关系。
   - manifest 增加对应 contents/counts。

7. 增加测试。
   - `semantic_knowledge` 接受后仍出现在 `/api/knowledge/search`。
   - `rule_preference` 和 `procedure_lesson` 通过 router 分流，暂时落到 `KnowledgeItem`，但能从 metadata/keywords/knowledge_type 看出目标 store。
   - dismissed proposal 不创建 source/item/page。
   - 未知 `target_store` 被拒绝，且不产生长期写入。
   - accept/dismiss 都有 decision 记录和 provenance 记录。
   - export 包含新增 proposal 字段、decision 文件和 provenance 关系。

### 验收标准

- semantic proposal 接受后能在知识搜索中出现。
- dismissed proposal 不写入任何长期 store。
- proposal 的 source/item/page/task provenance 仍然可导出。
- accepted/dismissed/re-routed proposal 能解释“为什么做出这个决定”。
- 前端候选记忆列表显示第一版字段。
- 测试覆盖 accepted、dismissed、未知 target_store、rule_preference、procedure_lesson 路径。
- `/api/knowledge/search`、`/api/knowledge/context`、task capsule、export 继续通过第一版验收。

### 当前落实状态

- 已在 `memory_core.protocol` 明确 Step 2 target store：`semantic_knowledge`、`rule_preference`、`procedure_lesson`，并建立 proposal type 到默认 store 的映射。
- 已在协议 ref kind 中加入 `store:`，用于 durable provenance 表达 `proposal_routed -> store:{target_store}`。
- 已在 `MemoryProposal` 第一版 schema / migration / response / export 中包含 `target_store`、`structured_payload_json`、`scope`、`confidence`、`review_note`、`decision_ref`。
- 已新增 durable `MemoryDecision` 与 `ProvenanceEvent` 表，并覆盖 `proposal_created`、`proposal_routed`、`proposal_accepted`、`proposal_dismissed`。
- `create_memory_proposal()` 会推断或校验 target store，并写入创建 decision/provenance；`accept_memory_proposal()` 已改为唯一通过 `MemoryRouter.accept_proposal()` 进入长期写入；`dismiss_memory_proposal()` 会写入 dismissal decision/provenance。
- `MemoryRouter.accept_proposal()` 已支持：
  - `semantic_knowledge`：写入 `KnowledgeItem`；`page_update` 写入 `KnowledgePage`。
  - `rule_preference`：先写入 typed `KnowledgeItem`，`knowledge_type` / keywords 标明 `rule_preference`。
  - `procedure_lesson`：先写入 typed `KnowledgeItem`，`knowledge_type` / keywords 标明 `procedure_lesson`。
  - 未知 target store、非 pending proposal、缺 title/body 的 proposal 明确拒绝，不产生长期写入。
- export 已包含 `memory_proposals.jsonl` routing/review 字段、`memory_decisions.jsonl`、durable provenance events，并补充 task/checkpoint/handoff/proposal 的导出关系。
- 前端 task workbench 的 MemoryProposal inbox 已显示 `targetStore`、`scope`、`confidence`、`decisionRef` / `reviewNote` 等第一版字段。
- 已新增/更新测试覆盖 semantic accept search、dismiss 不写入、未知 target store、重复 accept 拒绝、rule preference、procedure lesson、page update、decision/provenance/export 关系。
- 验证命令：
  - `$env:PYTHONPATH='.'; pytest server/tests` -> 39 passed。
  - `npm run build` -> passed。

## Step 3: Context Composer

### Step 2 后的当前基线

- Long-term proposal 写入入口已经收敛到 `MemoryRouter.accept_proposal()`。
- `KnowledgeItem` 现在承载三类 Step 2 typed store projection：普通 semantic fragment、`rule_preference`、`procedure_lesson`。
- `TaskMemoryStore` 已能返回 task state / recent task event 的 `MemorySlice`。
- `SemanticKnowledgeStore` 已能返回知识项 `MemorySlice`，但 page、rule、procedure 的优先级还没有由 composer 统一处理。
- `/api/knowledge/context` 形式上经过 `MemoryContextComposer`，但 composer 仍委托旧 `context.packs.build_context_pack()`，还没有真正用多 store slices 组合输出。
- ContextPack response 目前仍是 `protocolReminder + relatedPages + relatedItems + sourceExcerpts + budget + citationRefs`，尚未暴露 task state、rules、procedure lessons、decision refs、warnings 等第一版扩展字段。

### 目标方案

Step 3 的目标不是重写 retrieval，而是把 context 构建的控制权真正迁到 `MemoryContextComposer`：

1. 让 composer 直接调用 `MemoryRouter.retrieve()`，从 `SemanticKnowledgeStore`、`TaskMemoryStore` 和 Step 2 typed knowledge routes 获取 `MemorySlice`。
2. 在 composer 内完成统一过滤、分组、排序、dedupe、预算截断和 citation 聚合。
3. 保持 `/api/knowledge/context` 现有 query 参数可用，同时扩展 ContextPack 字段，让前端和未来 agent 可以区分 task state、rules、procedure lessons、related items/pages、source excerpts 和 warnings。
4. 把旧 `context.packs.build_context_pack()` 降级为可复用 helper 或逐步拆分，不再作为最终上下文编排入口。
5. 让 task-scoped context 通过 `taskSessionId` 或 `scope=task:{id}` 明确优先返回 task state / recent events，再返回 rules、procedure lessons 和 semantic knowledge。

### 约束与非目标

- 不新增 profile temporal graph 表；Step 3 不实现 `Entity`、`MemoryFact`、`MemoryRelation`、`MemoryConflict` durable model。
- 不引入外部 vector、graph、reranker 或 embedding 依赖；继续使用当前 SQLite FTS / RetrievalEngine 能力。
- 不改变 Step 2 的 reviewed write path；composer 只读，不接受 proposal，不写长期记忆。
- 不返回全库内容；所有 store retrieval 必须受 query、scope、limit、budget 约束。
- 不把 source full text 默认塞进 ContextPack；source excerpt 仍受数量和字符预算限制。
- 不做事后 redaction；scope、visibility、privacy label、capability 过滤必须在排序和输出前完成。
- 不让 task-scoped memory 泄露到 unrelated task；没有明确 task scope 时只返回 workspace-visible 内容。
- 不静默吞掉 slice 的 evidence/citation；事实性内容必须有 `citation_ref` 或 `evidence_refs`，reviewed long-term memory 尽量带 `decision_ref`。
- 不把 conflict 做成假实现；Step 3 只定义 warning 结构和透传 `conflict_refs`，真正 conflict durable lifecycle 留到 Step 4。

### 执行内容

- 让多个 store 统一返回 `MemorySlice`。
- composer 根据 query、scope、task id、预算限制拉取 slices。
- 在排序前先做 scope、visibility、capability、privacy label 过滤。
- 按优先级组合：protocol reminder、task state、rules、profile facts、pages/items、procedure lessons、source excerpts。
- 对敏感 slice 做 redaction，不能在 agent 已经看到后再补救。
- 对未解决 conflict 返回 warning，而不是假装只有一个正确事实。
- `/api/knowledge/context` 由 composer 输出第一版 ContextPack，后续直接扩展字段。
- 做 dedupe、预算截断、citation refs 汇总。

### 首批落地切片

1. 协议与 schema：
   - 增加 `MemoryContextQuery` 或扩展 `MemoryQuery`，包含 `task_session_id`、`scope`、`visibility`、`capabilities`、`max_chars`、各 store limit。
   - 扩展 `ContextPackResponse`：新增 `taskState`、`rules`、`procedureLessons`、`warnings`、`decisionRefs`，保留现有字段兼容前端。

2. Store 输出：
   - `SemanticKnowledgeStore` 继续返回普通 knowledge item slice，并把 `knowledge_type`、`decision_ref` 信息放入 metadata 或 slice 字段。
   - 增加 page slice 支持，或由 composer 复用现有 page 匹配 helper 输出 page section。
   - `TaskMemoryStore` 在 task scope 下返回 task state 和 recent events，不参与无 scope 的全局普通 context。
   - rule/preference 与 procedure/lesson 初期从 `KnowledgeItem.knowledge_type` 过滤，不创建新表。

3. Composer 行为：
   - 先过滤 scope / visibility / privacy / capability。
   - 再按固定优先级组装：protocol reminder -> task state -> rules -> procedure lessons -> semantic pages/items -> source excerpts。
   - 用 ref、evidence refs、source item id 做 dedupe。
   - 预算按 section 截断，最后统一生成 `citationRefs`、`decisionRefs`、`warnings`。

4. 前端：
   - context 使用方按新字段渲染，但保留 `relatedPages` / `relatedItems` / `sourceExcerpts` 的现有体验。
   - 对 warning、stale task、private filtered count 只做清晰显示，不做复杂 review UI。

### 验收标准

- ContextPack 不返回全库内容。
- 每条事实性内容都有 citation ref 或 evidence ref。
- review 过的长期记忆尽量带 decision ref。
- source excerpt 仍受数量和字符预算限制。
- task-scoped query 能优先返回任务状态。
- private / unrelated task / insufficient capability 的记忆不会进入 ContextPack。
- 有活跃矛盾时 ContextPack 会返回 conflict 信号。
- 前端字段按第一版 ContextPack 契约演进。
- 后端测试覆盖：task-scoped 优先 task state、rule/procedure section、budget 截断、source excerpt 限制、unrelated task 过滤、citation/decision refs。
- 前端构建通过，ContextPack 新字段为空时不破坏旧页面。

## Step 4: Profile Temporal Graph Store

### 执行内容

- 新增 `Entity`、`MemoryFact`、`MemoryRelation`、`MemoryConflict` 模型。
- 支持 `valid_at`、`invalid_at`、`superseded_by`、`confidence`、`evidence_refs`。
- 新增 proposal types：`profile_fact`、`entity_relation`、`fact_supersession`。
- 先用本地 SQLite/SQLModel 实现，不接外部图数据库。
- 在 composer 中只返回当前有效事实，除非显式请求历史。
- 冲突事实先进入 `MemoryConflict`，由用户或显式 trusted policy 处理。
- supersession、invalidation、conflict resolution 都写入 decision/provenance。

### 验收标准

- 用户确认的 profile fact 可以被写入并检索。
- 新事实能 supersede 或 conflict 旧事实，旧事实不被物理删除。
- 无 evidence ref 的长期事实不能进入 active 状态。
- 未解决冲突不会被普通检索静默隐藏。
- export 包含 entities、facts、relations、conflicts 和 provenance。

## Step 5: 导出与重建保证

### 执行内容

- 扩展 export bundle，加入 graph/profile/rules/procedures 文件。
- 为 accepted proposal、superseded fact、conflict resolution 写 provenance。
- 增加 `memory_decisions.jsonl`。
- provenance 支持可选 hash chain 字段：`hash`、`previous_hash`。这只是审计链，不是 agent 共识链。
- 提供 retrieval projection rebuild 服务或命令。
- 明确 durable store 与 derived projection 的边界。

### 验收标准

- 删除 FTS/derived index 后可以重建。
- 重建后搜索和 context 行为保持等价。
- export 可在不启动应用的情况下人工检查。
- manifest 中列出所有 durable store 的文件、版本和数量。
- export 能回答每条长期记忆“从哪里来、为什么留下、谁能看、是否被替代或失效”。

## Step 6: Agent Protocol 与 MCP

### 执行内容

- 暴露稳定 agent tools：`get_context_pack`、`get_source_excerpt`、`list_active_tasks`、`record_task_event`、`update_task_state`、`create_checkpoint`、`get_handoff_pack`、`propose_memory`、`list_memory_proposals`。
- 工具只返回 refs、citation refs 和预算化内容。
- agent 只能创建 proposal，不能直接写长期 memory。
- 对 task close、long-term write、delete evidence 保持显式限制。
- 工具调用要带 caller/task/scope 信息，便于权限过滤和审计。
- 需要能返回 conflict warning、stale warning、permission denied、budget exceeded 等结构化错误。

### 验收标准

- agent 无法绕过 review gate 写长期 memory。
- 普通工具调用不会返回 full-library dump。
- handoff 仍然包含 stale warning。
- agent 看不到没有权限的 private/profile/source 记忆。
- agent 不能私自解决冲突或删除证据。
- 工具错误信息能区分权限、缺失 ref、stale task 和预算不足。

## Step 7: Review Workbench UI

### 执行内容

- 建立 Memory Proposal Inbox。
- 增加 Profile Facts、Conflicts、Rules、Procedures、Task Capsule、Knowledge Pages、Source Evidence 等视图。
- 支持接受、编辑、改路由、supersede、reject。
- 每个记忆显示 evidence refs、状态、来源任务或 source。
- 每个长期记忆显示 decision history：为什么创建、谁确认、是否替代过旧记忆。
- 支持调整 scope、visibility、privacy labels。
- 提供导出入口。

### 验收标准

- 用户能看清每条记忆为什么存在。
- 用户能撤销、失效或 supersede profile fact。
- 冲突记忆不会被静默覆盖。
- review 操作能留下 provenance。
- 用户能查看 agent 最近读取了哪些 durable memory。
- 用户能把敏感 source purge 或降低可见性。
- 用户离开产品前可以导出完整记忆包。

## Step 1 完成后的决策

Step 1 已经有独立协议层和只读 store。Step 2 直接采用第一版 routing/decision/provenance schema，不保留旧 proposal schema。

- `MemoryProposal` 第一版就包含 `target_store`、`structured_payload_json`、`scope`、`confidence`、`review_note`、`decision_ref`。
- 前端响应直接使用第一版字段。
- `MemoryRouter.accept_proposal()` 是 Step 2 的唯一长期记忆写入入口。
- decision / provenance 先覆盖 proposal accept/dismiss/routing，不提前扩展到 profile graph。

核心判断标准只有一个：新协议层应该让后续改动更容易，而不是让当前行为变得更脆。

## 未来设计自检问题

每次新增 memory 功能前，都要回答：

1. 这条记忆属于哪个 durable store？
2. 它的 evidence ref 是什么？
3. agent 能直接写，还是只能 propose？
4. 它是事实、规则、流程、任务状态、笔记、source，还是 derived projection？
5. 它会不会 stale、invalid、superseded、archived？
6. 为什么它值得进入长期记忆，而不是只停留在短期上下文？
7. 谁能读它？scope、visibility、privacy label 是什么？
8. 两个 agent 对它产生矛盾时，走 conflict、supersession 还是 scoped alternative？
9. 它需要强一致、最终一致，还是 stale-aware 即可？
10. 它能否导出给另一个工具，并保留元记忆和 provenance？
