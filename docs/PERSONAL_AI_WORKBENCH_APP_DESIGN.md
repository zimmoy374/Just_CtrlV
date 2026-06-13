# Personal AI Workbench App Design

这份文档定义 `second brain` 下一阶段的产品方向。对用户来说，它不是一个 `kernel`，而是一个稳定可用的个人 AI 工作台应用。内部可以保留 memory core、agent runtime、retrieval pipeline 等工程模块，但产品表达必须始终围绕用户怎样在应用里完成真实工作。

## 北极星

`second brain` 要升级为：

> 本地优先的个人 AI 工作台应用：用户在一个稳定应用里管理知识、项目、任务、计划、证据、决策和输出；用户自行配置 AI API，并能按项目、任务和阶段分配不同 AI；应用负责上下文、权限、审查、长任务续跑、流程沉淀和可视化掌控。

核心判断问题：

> 这项设计是否让用户的知识、项目状态、工作流程和 AI 协作更可靠、更可控、更容易复用？

如果答案是否定的，默认降级、延后或删除。

## 产品不是这些

- 不是单纯的个人知识库。知识库只是平时状态和长期资产层。
- 不是多 agent 炫技平台。AI worker 是任务能力，不是产品主语。
- 不是让 AI 自动接管电脑的黑盒。所有高风险执行都要有计划、权限、预算和审计。
- 不是企业协同 SaaS。第一目标是独立开发者和个人工作流。
- 不是 Claude Code、GenericAgent、OpenClaw 的复制品。只吸收可落地的工作模式。

## 外部模式借鉴

### Claude Code Ultracode / Dynamic Workflows

官方文档把 dynamic workflow 定义为由脚本编排大量 subagents 的后台运行机制，适合代码库审计、大迁移和交叉验证研究；workflow 的计划被写入脚本，运行时在后台执行，session 仍然可响应。文档也明确区分 subagent、skill、agent team 和 workflow：workflow 的优势是计划在脚本里，中间结果在脚本变量里，而不是一直塞进对话上下文。

可借鉴：

- **Workflow Run**：长任务不再只是一次聊天，而是一个有 run id、阶段、预算、状态和产物的后台运行对象。
- **Plan before fan-out**：启动复杂工作前先生成阶段计划，用户能查看、批准、拒绝或调整。
- **Background progress**：用户可以继续操作应用，同时看到阶段进度、worker 数、耗时、token/cost。
- **Scoped pilot first**：大任务先小范围试跑，例如一个目录、一个模块或一个样本集。
- **Independent verification**：重要任务拆出独立 review/check 阶段，不让同一个 AI 自说自话。
- **Saved workflow**：跑通后可保存为可复用 workflow template。

不能照搬：

- 不默认开启超高成本模式。
- 不允许后台无限 fan-out。
- 不让 worker 自动越权访问 private/sensitive 内容。
- 不把 workflow script 当成用户必须理解的唯一界面。
- 不让文件编辑、命令执行、外部调用绕过应用权限。

### Claude Code Goal

Claude Code 的 `/goal` 模式把目标写成可验证完成条件，让系统持续执行，直到条件满足或需要介入。这个思路对个人工作台非常重要：长任务必须有明确停止条件，而不是“继续优化”。

可借鉴：

- **Goal Condition**：每个长任务必须有可检查的完成条件。
- **Evaluator Loop**：每个阶段结束后由轻量 evaluator 检查是否达成条件。
- **Stop Reason**：完成、预算耗尽、权限缺失、测试失败、等待用户、证据不足都要明确记录。
- **Resumability**：暂停后继续时从 durable run state 恢复，而不是依赖聊天上下文。

不能照搬：

- 不把 goal 设计成无限自主循环。
- 不只依赖模型自评。代码任务必须接测试、lint、build 或人工验收；知识任务必须接证据和 Review Gate。

### GenericAgent / Goal Hive

GenericAgent 的公开 README 强调分层记忆、少量原子工具、自主执行循环，以及把完成过的任务路径沉淀成可复用 Skill/SOP。社区里提到的 Goal Hive 可理解为长目标的 master-worker 模式：Master 拆解和验收，多个 worker 并行推进。

可借鉴：

- **Context information density**：长任务靠高密度上下文，而不是无限拉长上下文。
- **Layered memory**：meta rules、insight index、facts、SOP/skills、session archive 分层读取。
- **Crystallize after proof**：重复流程只有在真实跑通、可验证之后才沉淀为 Skill、workflow template 或 automation。
- **Master-worker shape**：复杂任务可以有 planner/master、researcher、builder、reviewer、summarizer 等角色，但它们由应用的 run plan 管理。
- **Minimal atomic tools**：工具入口保持少而稳，高级能力通过 workflow/skill 组合出来。

不能照搬：

- 不允许 AI 自动把任意探索结果写入长期记忆。
- 不允许 AI 动态创建高风险工具后直接常驻使用。
- 不把“自进化”定义为无人审查的自我修改；应用里的自进化必须走候选、证据、评估和用户确认。

## 产品表面

第一版应用保留四个主入口。

| 入口 | 用户问题 | 主要对象 |
| --- | --- | --- |
| Knowledge | 我保存和沉淀了什么？ | Source、Memory、Page、Procedure、Review |
| Projects | 我现在在做什么项目，结构和进度如何？ | Project、Task、Plan、Decision、Code Map |
| AI Workspace | 我让哪个 AI 帮我做什么，它能读什么、写什么？ | AI Provider、AI Role、ContextPack、Run |
| Review | 哪些东西需要我确认后才进入长期资产？ | MemoryProposal、WorkflowCandidate、ProofComment、AutomationCandidate |

应用的默认第一屏不应该是营销页，也不应该是全局 dashboard。建议是 **Projects + current work**：左侧项目和任务，中央当前任务/计划/AI workspace，右侧 context trace 和 review queue。

## AI 配置是一等公民

用户必须能在应用里配置自己的 AI API，并按任务分配不同 AI。

### AI Provider

保存模型调用入口。

字段建议：

- `name`
- `providerType`: `openai_compatible`、`anthropic_messages`、`local`、`custom`
- `baseUrl`
- `apiKeyRef`: 只保存加密引用，不在普通导出中明文暴露
- `defaultModel`
- `supportsVision`
- `supportsAudio`
- `supportsTools`
- `supportsStructuredOutput`
- `maxContextTokens`
- `costHint`
- `rateLimitHint`
- `isEnabled`

### AI Role Preset

把模型配置和任务角色绑定。

示例：

- `planner`: 擅长拆任务、写计划、发现风险
- `coder`: 擅长代码实现和局部调试
- `reviewer`: 擅长审查、安全、回归风险
- `researcher`: 擅长资料检索和交叉验证
- `summarizer`: 擅长压缩、handoff、Proof 文档
- `voice_interpreter`: 擅长把口述整理成目标、约束和下一步
- `workflow_miner`: 擅长从历史记录发现重复流程候选

每个 role preset 需要配置：

- 默认 provider/model
- 可读 memory scope
- 可用 tools
- 最大预算
- 是否允许后台运行
- 是否允许写文件或执行命令
- 是否只能创建 proposal

### Task AI Assignment

任务上可以设置：

- 默认 AI
- planning AI
- execution AI
- review AI
- summarization AI
- voice AI
- workflow mining AI

阶段可以覆盖任务默认设置。这样用户可以把便宜模型用于总结，把强模型用于架构审查，把本地模型用于敏感资料整理。

## 核心领域对象

### Project

用户正在维护的长期工作空间。

- Durable: 是
- 包含：repo/path、目标、代码图谱、任务、计划、决策、证据、Proof 文档
- 可重建：索引、代码依赖图、搜索解释

### Task

用户可见的工作单元，不再只是 agent 协议内部状态。

- Durable: 是
- 状态：`draft`、`ready`、`running`、`waiting_user`、`blocked`、`reviewing`、`done`、`archived`
- 包含：目标、完成条件、所属项目、AI assignment、计划、runs、decisions、artifacts

### Plan

给 AI 执行和给人理解的结构化计划。

- Durable: 是
- 形态：Markdown/spec + structured steps
- 派生：Proof document 可以由 Plan 生成
- 状态：`draft`、`approved`、`running`、`revised`、`superseded`

### GoalRun

长任务执行实例。

- Durable: 是
- 用途：让 AI 围绕可验证条件持续推进
- 必填：goal、completion condition、budget、assigned AI、allowed tools
- 状态：`planned`、`approved`、`running`、`paused`、`waiting_user`、`verifying`、`completed`、`failed`、`stopped`
- Stop reason：`condition_met`、`budget_exhausted`、`permission_needed`、`test_failed`、`blocked`、`user_stopped`、`low_confidence`

### WorkflowRun

多阶段、多 worker 的长任务实例。

- Durable: 是
- 包含：phase list、worker assignments、intermediate artifacts、progress、cost、logs、verification
- 只在任务足够复杂时启用
- 每个 phase 可以指定不同 AI role

### WorkflowTemplate

可复用的长任务编排。

- Durable: 是，但必须经过 Review
- 来源：用户创建、跑通的 WorkflowRun 保存、Workflow Miner 建议
- 状态：`candidate`、`approved`、`deprecated`

### ProofDocument

给人看的计划、spec、结果或决策文档。

- Durable: 是
- 来源：Plan、Task summary、Decision log、Spec
- 支持：分享链接、inline comment、版本、评论回流
- 评论必须回写为 evidence 或 task event，而不是直接改长期记忆

### WorkflowCandidate

30 天工作回顾或任务结束后产生的流程沉淀候选。

- Durable: 是，进入 Review
- 推荐形式：`prompt_template`、`skill`、`ai_role_preset`、`workflow_template`、`automation`、`checklist`、`skip`
- 必须带证据：日期、任务、重复次数、收益、已有覆盖检查

## 长任务运行模式

应用不应该只有一种“run agent”按钮。建议分四种模式，按风险和复杂度递进。

### 1. Chat Assist

普通对话式协助。

- 单个 AI
- 低预算
- 不后台运行
- 适合问答、局部总结、轻量计划

### 2. Goal Run

围绕完成条件持续推进。

- 一个主 AI
- 可跨多轮
- 每轮结束进行 evaluator check
- 适合修一个 bug、补一个小功能、整理一份文档

### 3. Workflow Run

阶段化长任务。

- app 生成或加载 phase plan
- 用户批准后运行
- 每个 phase 可分配不同 AI
- 支持暂停、恢复、重跑某阶段
- 适合代码库审计、迁移、复杂调研、Proof 生成

### 4. Hive Run

多 worker 并行长任务。

- 只用于高价值、可分片、可验证任务
- master 只负责拆解、分配、收敛和验收
- worker 只拿最小上下文和明确输出格式
- reviewer 独立检查 worker 结果
- 必须有预算上限和 worker 上限

第一版不要直接实现完整 Hive Run。先实现 Goal Run 和轻量 Workflow Run，等可视化、预算、权限和 verification 稳定后再扩展。

## 长任务控制台

用户需要能掌控全局，而不是看 AI 输出刷屏。

### Run Timeline

显示：

- 阶段
- 当前状态
- 负责 AI
- 输入上下文
- 输出 artifact
- verification 结果
- token/cost
- stop reason

### Worker Board

用于 Workflow/Hive Run：

- worker 名称
- 分配任务
- 模型
- 进度
- 最近动作
- 输出摘要
- 是否需要用户介入

### Context Trace

每次 AI 调用都显示：

- 读取了哪些 memory/task/source/code refs
- 哪些内容被权限过滤
- 哪些内容因为预算被截断
- 为什么选择这些上下文

### Decision Timeline

显示：

- 用户确认的关键决策
- AI 提议但未确认的假设
- 被推翻的旧决策
- 对应证据和任务

## 30 天 Workflow Miner

用户描述的这段能力应该成为应用内正式功能，而不是一次性 prompt。

入口：

```text
Review -> Analyze My Workflows
```

默认范围：

- 最近 30 天 Codex/AI sessions 和 task summaries
- 不足 30 天则读取所有可用历史
- Codex Memories / accepted procedures / task digests
- Chronicle 或外部活动记录，如果启用
- 已有 skills、AI role presets、workflow templates、automations

输出候选清单：

- 重复出现的工作流
- 证据和日期
- 频率和置信度
- 已有覆盖情况
- 推荐形式
- 预期收益
- 推荐创建或 Skip 的理由

创建门槛：

- 至少出现两次，或非常可能继续重复
- 输入稳定
- 步骤可重复
- 有明确输出或停止条件
- 现有工具没有很好覆盖
- 封装后能提升速度、质量、一致性或可靠性

候选形式：

| 形式 | 何时使用 |
| --- | --- |
| Prompt Template | 步骤简单，只需要稳定提示词 |
| Skill | 可复用操作手册，需要人工或 AI 遵循 |
| AI Role Preset | 同类任务反复需要同一类模型/权限/工具 |
| Workflow Template | 多阶段、可验证、可复跑 |
| Automation | 定时、周期性、事件触发 |
| Checklist | 主要是人工执行和验收 |
| Skip | 证据不足、太敏感、太零散、收益不明 |

所有创建都必须进入 Review。高置信度项目也不应直接成为长期规则。

## Proof 协作层

`plan.md` 适合给 AI 和终端看，Proof 适合给人看。

流程：

```text
Plan / spec / decision log
-> Generate ProofDocument
-> Share link
-> Inline comments
-> Comments become task events and evidence
-> AI receives comment ContextPack
-> Plan revised with provenance
```

第一版 Proof 不需要做完整团队协同 SaaS。只需要：

- 本地或局域网可打开的文档链接
- inline comment
- 评论回流到 task
- AI 可读取评论摘要
- 每次 AI 修改 plan/spec 都保留版本

## Voice Work Mode

语音入口属于 AI Workspace，不是普通转写插件。

目标：

- 用户可以含糊地讲想法
- 系统结合当前 project/task/plan/code context 整理成结构化输入
- AI 不只转文字，而是补全省略、去重、识别犹豫、保留不确定点

输出类型：

- task goal
- constraints
- plan draft
- spec draft
- decision proposal
- review request
- workflow miner seed

语音整理结果不能直接写长期记忆。它先成为 source evidence 或 task note，再由 Review Gate 决定是否沉淀。

## Voice-to-Work Intent Engine

语音能力不能做成普通 STT。普通 STT 只把声音压扁成文字，效果和打字差不多；本应用要做的是把口述、犹豫、改口、停顿、语气和当前工作上下文一起解释成可确认、可追溯、可执行的工作意图。

目标不是“语音助手”，而是：

> Voice-to-Work Intent Engine：把用户含糊的口述思考，转成结构化的 Task、Plan、Decision、Review request 或 Workflow seed，同时保留不确定性和证据。

### 双轨架构

语音系统分两条轨道，避免在实时自然度和工作可靠性之间二选一。

| 轨道 | 用途 | 关键能力 |
| --- | --- | --- |
| Audio-native realtime | 自然语音对话、打断、快速反馈 | 直接把音频流送入 realtime/audio-native 模型，支持 VAD、barge-in、低延迟音频输出 |
| Workbench-grade interpreter | 项目工作、模糊想法整理、计划和决策生成 | 原始音频 + transcript + timestamps + speech markers + ContextPack -> VoiceIntentDraft |

第一条轨道让交互自然，第二条轨道让结果可靠。面试展示时重点讲第二条：它不是“会说话”，而是能把用户未成形的想法变成可审查的工作对象。

### 工程难点

本地或本地优先语音系统的难点必须正面解决，而不是用一句“先转文本”绕开。

- **实时音频流**：麦克风采样、分片、编码、播放缓冲和本地/云端推理延迟都要可控。
- **轮次判断**：VAD 只能判断有没有声音，不能判断用户是否说完；长停顿可能是思考，不一定是结束。
- **打断和全双工**：AI 正在说话时，用户插话要立刻停播、保留已说内容、重建上下文。
- **回声消除**：扬声器播放的 AI 声音可能被麦克风重新录入，需要 echo cancellation 或明确耳机模式。
- **纠结识别**：停顿、重复、改口词、语速变化、低置信度 span 都是有价值信号，不能被清洗掉。
- **本地模型推理**：STT/TTS/realtime audio 模型涉及 GPU、量化、流式推理、模型加载和降级策略。
- **任务系统同步**：语音结果必须能进入 Task、Plan、Review、SourceItem 和 Provenance，而不是只停留在聊天框。
- **可评测性**：必须能测不确定点召回、改口识别、意图结构化、延迟和错误写入率。

### 数据流

```text
microphone audio
-> VoiceArtifact(raw audio, hash, duration, format)
-> STT transcript with word/segment timestamps
-> SpeechMarker extraction
-> ContextPack(project/task/plan/code/memory)
-> VoiceIntentDraft
-> user confirmation
-> Task / Plan / Review / SourceItem / Provenance
```

音频和转写都是证据。SpeechMarker 和 VoiceIntentDraft 是派生结果。长期记忆仍然只能通过 Review Gate。

### Speech Markers

Voice Interpreter 要显式提取这些信号：

- `long_pause`：长停顿，可能代表思考、犹豫或新段落。
- `self_repair`：例如“不对”“等等”“我的意思是”，表示前一句被修正。
- `hedge`：例如“可能”“大概”“我感觉”，表示低确定性。
- `repeat`：重复词或重复短语，可能是强调或卡住。
- `emphasis`：音量、语速或重音变化，提示核心偏好。
- `low_asr_confidence`：ASR 置信度低，不能直接当确定事实。
- `context_conflict`：口述内容和当前项目记忆/计划冲突，必须让用户确认。

这些 marker 不一定全部来自单一模型。第一版可以由 STT timestamps、文本规则、音频能量/语速分析和 LLM 二次判断组合得到；后续再替换为更强的 audio-native provider。

### VoiceIntentDraft

语音解释层的输出不是“清洗后的文字”，而是结构化草稿：

```json
{
  "cleanedThought": "用户希望语音功能理解模糊表达，而不是普通转文字。",
  "commitments": [
    "语音不是普通 STT",
    "系统要保留纠结和不确定性"
  ],
  "uncertainties": [
    "是否优先实现实时语音还未确认",
    "哪些 speech markers 必须进入第一版还需取舍"
  ],
  "selfRepairs": [
    {
      "original": "语音转文字",
      "revision": "理解模糊表达的原本",
      "evidence": "用户使用“不对/我的意思是”类修正表达"
    }
  ],
  "suggestedActions": [
    "新增 Voice-to-Work Intent Engine 设计",
    "把 VoiceIntentDraft 接入 Task/Plan/Review"
  ],
  "questionsToConfirm": [
    "是否先做录音后高质量整理，再做实时可打断对话？"
  ]
}
```

UI 也必须承认不确定性，分成三块展示：

- 我确定听懂的。
- 我推测你可能想表达的。
- 需要你确认的。

### Provider 策略

语音 provider 只能是可替换能力，不能绑死产品。

| Provider 类型 | 候选 | 用途 |
| --- | --- | --- |
| STTProvider | faster-whisper、OpenAI、Boson STT、本地 ASR | 生成 transcript、timestamps、confidence |
| TTSProvider | Higgs Audio v3、OpenAI TTS、ElevenLabs、本地 TTS | 生成自然语音输出 |
| RealtimeVoiceProvider | OpenAI Realtime、Gemini Live、Moshi 类本地模型 | 低延迟、可打断、audio-native 对话 |
| MarkerProvider | 本地规则 + LLM + 音频特征分析 | 提取停顿、改口、强调、不确定性 |

Higgs Audio v3 适合做强 TTS provider，负责“AI 说得自然”。应用的核心差异化在 Voice Interpreter，负责“AI 听得懂用户工作中的模糊想法”。

### 质量指标

语音功能必须用指标证明不是玩具 demo。

- `turnDetectionAccuracy`：轮次判断是否把思考停顿误判成结束。
- `bargeInLatencyMs`：用户打断 AI 到停止播放的延迟。
- `firstUsefulDraftLatencyMs`：录音结束到出现可用 VoiceIntentDraft 的时间。
- `selfRepairRecall`：改口/修正表达被识别的比例。
- `uncertaintyRecall`：不确定点被保留而不是被 AI 擅自确定的比例。
- `intentStructuringAccuracy`：目标、约束、下一步、决策候选的结构化准确率。
- `contextGroundingRate`：VoiceIntentDraft 是否引用当前 task/project/context。
- `falseMemoryWriteRate`：语音内容绕过 Review 写入长期记忆的比例，必须为 0。

第一版即使不是全 realtime，也必须达到：原始音频可回放、transcript 有时间戳、marker 可解释、draft 可确认、写入路径可审计。

## 代码全局可视化

独立开发者需要掌控复杂项目，但不需要一个全库大图谱玩具。

优先做四个可行动视图：

- **Project Map**：模块、入口、依赖、关键文件、最近变更。
- **Impact View**：这次计划会影响哪些模块、测试和文档。
- **Risk View**：未测区域、权限边界、复杂依赖、历史失败点。
- **Run-linked Code View**：每个 AI run 读了哪些文件、改了哪些文件、验证了什么。

所有图都必须能点回文件、任务、证据或决策。不能点回来源的可视化默认不做。

## 权限和安全边界

用户自带 API 和多 AI 分配会带来新风险。

必须保留这些边界：

- API key 加密保存，导出时默认不含明文。
- 每个 AI role 有独立 capability profile。
- 默认 AI 只能读 work scope。
- private/profile/sensitive 需要明确启用。
- AI 只能提出长期记忆 proposal，不能直接接受。
- 高风险 tool 需要任务级授权。
- 后台 run 必须有预算上限、停止条件和可见进度。
- AI 创建的新 workflow、skill、automation 都先进入 Review。
- 每次 AI 读写都记录 provenance。

## 与现有项目的关系

现有能力不推倒重来，而是重新归位。

| 现有能力 | 新定位 |
| --- | --- |
| SourceItem / KnowledgeItem | Knowledge 的 durable assets |
| Review Gate | 所有长期沉淀的统一审查入口 |
| ContextPack / selectionTrace | AI Workspace 的上下文控制和解释层 |
| TaskSession / TaskEvent / Checkpoint | 升级为用户可见 Task / Run 的基础 |
| Agent Protocol / CLI / MCP | 外部 agent 和本地工具接入层 |
| Retrieval eval / usefulness eval | 应用可靠性的证据层 |
| Search network | 降级为局部 Context/Project explanation |

需要改变的是产品表面：从“agent memory core demo”转为“稳定个人 AI 工作台应用”。

## MVP 路线

### Phase 0：产品定位和文档冻结

目标：

- README 从 memory core 叙事调整到 personal AI workbench app。
- 保留内部架构文档里的 memory core，但不再作为产品名称。
- 增加本文件作为下一阶段应用级设计入口。

验收：

- 新用户能在 1 分钟内理解：这是一个可配置 AI 的个人工作台应用。

### Phase 1：AI Provider 和 Role Preset

目标：

- 用户可以配置自己的 API。
- 用户可以创建 AI role preset。
- Task 可以选择默认 AI。

最小实现：

- Settings: AI Providers
- Settings: AI Roles
- encrypted key ref 或本地 env ref
- provider health check

验收：

- 不同任务可以选择不同 provider/model。
- 默认 work capability 不泄露 private/profile。

### Phase 2：用户可见 Project / Task

目标：

- 把 task 从 agent 内部状态升级成应用工作对象。
- 当前 handoff/checkpoint 能继续复用。

最小实现：

- Projects 页面
- Task detail
- goal、completion condition、assigned AI、plan、events、checkpoints

验收：

- 用户能从 UI 创建任务、指定 AI、查看进度和下一步。

### Phase 3：Goal Run

目标：

- 长任务可以围绕完成条件持续推进。

最小实现：

- GoalRun 表或服务对象
- evaluator check
- budget
- pause/resume/stop
- run timeline

验收：

- 一个文档任务或小代码任务能自动推进到可验证完成条件，并留下 checkpoint。

### Phase 4：Workflow Run

目标：

- 支持阶段化、多 AI 分配、可重跑的长任务。

最小实现：

- phase plan
- user approval
- per-phase AI role
- artifacts
- verification phase
- save as template

验收：

- 代码审计、Proof 生成或 workflow mining 可以作为 workflow run 执行。

### Phase 5：Workflow Miner

目标：

- 把“回顾最近 30 天，找重复流程，只创建高置信度项目”变成应用功能。

最小实现：

- 读取 task events、checkpoints、accepted procedures、skills/automations registry
- 输出 candidates
- Review 后创建 prompt template / skill / AI role / workflow / automation

验收：

- 至少能在当前项目历史里找出真实重复流程候选，并正确 Skip 证据不足项。

### Phase 6：Proof 和 Voice

目标：

- 打通人类协作和语音输入。
- 语音不是普通 STT，而是 Voice-to-Work Intent Engine。

最小实现：

- Plan -> ProofDocument
- inline comment -> task event
- VoiceArtifact 保存原始音频、hash、duration、format
- STT transcript 带 segment/word timestamps
- SpeechMarker 提取 long pause、self repair、hedge、repeat、low confidence
- VoiceIntentDraft 输出 commitments、uncertainties、self repairs、questionsToConfirm、suggestedActions
- 用户确认后写入 Task/Plan/Review，不能直接写长期记忆

验收：

- 人类评论能进入 AI loop。
- 语音整理结果能作为 plan/spec/review request 的草稿。
- 至少有一组评测样例覆盖改口、犹豫、长停顿、上下文冲突和低置信度转写。
- `falseMemoryWriteRate` 必须为 0。

## 第一批不做

- 不做完整多租户团队 SaaS。
- 不做无限多 worker 的 Hive Run。
- 不做全自动自我改造。
- 不做全局知识图谱页面。
- 不做需要云同步才能工作的功能。
- 不做没有 Review 的长期记忆写入。
- 不做没有预算、没有停止条件的后台 run。

## 设计结论

长任务处理值得借鉴，但要应用化：

- 从 Ultracode 借 **workflow as managed background run**。
- 从 Dynamic Workflows 借 **计划前置、用户批准、进度可见、可保存复用、独立验证**。
- 从 Goal 借 **可验证完成条件和持续推进**。
- 从 Goal Hive 借 **master-worker 的任务分解和收敛**，但先只做受控 Workflow Run。
- 从 GenericAgent 借 **分层记忆、上下文密度、从已验证轨迹沉淀流程**。

最终产品不是“帮你开很多 agent”，而是：

> 用户在一个稳定应用里定义目标、选择 AI、控制上下文、运行长任务、审查结果、沉淀流程，并在下次工作时复用这些资产。

## 参考资料

- Claude Code Dynamic Workflows docs: https://code.claude.com/docs/en/workflows
- Anthropic announcement, Introducing dynamic workflows in Claude Code, May 28, 2026: https://claude.com/blog/introducing-dynamic-workflows-in-claude-code
- Claude Code Week 20 docs, `/goal` release notes: https://code.claude.com/docs/zh-CN/whats-new/2026-w20
- Claude Code LLM gateway configuration: https://code.claude.com/docs/en/llm-gateway
- GenericAgent GitHub repository: https://github.com/lsdefine/GenericAgent
