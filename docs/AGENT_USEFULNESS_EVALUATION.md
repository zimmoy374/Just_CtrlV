# Agent Usefulness Evaluation Protocol

这份文档定义如何证明 `second brain` 对外部 agent 接入是真的有用，而不是一个看起来高级但无法改善任务结果的 demo。

核心目标：

> 外部 agent 接入本地 Agent Memory Kernel 后，是否比不接入更快、更准、更少重复、更少问人、更少误写、更少泄露，并且能可靠接手另一个 agent 的工作状态。

这不是模型能力 benchmark，也不是 UI 演示评分。它评估的是 memory protocol、handoff、ContextPack、Review Gate 和安全边界对 agent 工作流的实际增益。

## 有效性的定义

一个外部 agent 接入本系统后，如果满足以下条件，才算“有效”：

1. 它能按稳定协议快速接入，不需要读数据库或源码。
2. 它能从另一个 agent 的状态中恢复当前目标、已完成、下一步、决策、风险和涉及文件。
3. 它继续任务时，比没有 memory 的 baseline 更少重复劳动、更少问用户、更少改错文件。
4. 它拿到的 ContextPack 是相关、可引用、低噪音、遵守预算的。
5. 它提出的长期记忆候选有证据、少重复、用户愿意接受。
6. 它不能绕过 Review Gate，不能默认读取私密内容，所有读写都有 provenance。

如果只做到“接口能返回 JSON”或“搜索能返回内容”，不算有效。

## Baseline 设计

所有 usefulness 指标必须和 baseline 比较。没有 baseline 的高分只能说明系统能跑，不能说明系统有价值。

建议 baseline：

| Baseline | 含义 | 目的 |
| --- | --- | --- |
| `no_memory` | 只给 agent 当前用户请求 | 测系统是否真的补足跨 session 状态 |
| `readme_only` | 给 agent README 和当前请求 | 测项目文档是否已经足够，memory 是否有额外价值 |
| `chat_summary_only` | 给 agent 一段普通聊天摘要 | 测 handoff 是否优于自然语言摘要 |
| `full_context_uncontrolled` | 给 agent 大量未过滤上下文 | 测 ContextPack 是否比“全塞进去”更准、更安全 |
| `second_brain_protocol` | 只能通过 instructions/tools/context/handoff/source excerpt 接入 | 目标方案 |

最重要的比较不是绝对分，而是：

```text
Continuation Lift = second_brain_protocol 成功率 - 最强 baseline 成功率
```

## 指标总览

推荐总分：

```text
Agent Usefulness Score
- Protocol Usability: 15%
- Handoff Recovery: 20%
- Task Continuation Lift: 25%
- Context Utility: 15%
- Memory Write Quality: 10%
- Safety Boundary: 15%
```

Safety 是硬门槛，不只是加权项：

- 出现 private/profile/sensitive 泄露，最高证据等级降级。
- 暴露直接长期记忆写入能力，usefulness score 最高只能记为 demo 级。
- 没有 baseline 对照，不能写“提升”，只能写“内部功能通过”。

## 1. Protocol Usability

问题：外部 agent 是否能方便、稳定地接入。

测试方式：

1. agent 只允许读取 `/api/agent/instructions`。
2. agent 根据 instructions 读取 `/api/agent/tools`。
3. agent 根据 tools 调用 `/api/agent/context`。
4. agent 在错误参数、缺失 task、权限不足时能否根据错误恢复。

指标：

| 指标 | 含义 |
| --- | --- |
| `callsToFirstContext` | 拿到第一个可用 ContextPack 所需调用次数 |
| `protocolCompletionRate` | 是否能按 instructions 完成推荐调用顺序 |
| `errorActionabilityRate` | 错误 code/message/refs 是否足以指导下一步 |
| `schemaStability` | 字段是否稳定、命名是否自解释 |
| `sourceReadDiscipline` | 是否只在拿到 `source:` ref 后读取 excerpt |

合格线：

- 3 次调用内拿到可用 ContextPack。
- 不需要读取数据库、导出包或源码。
- 失败响应包含明确 `code`、`message`、`refs`。

## 2. Handoff Recovery

问题：一个 agent 的工作状态是否能被另一个 agent 接上。

测试方式：

1. Agent A 完成一段任务，写入 task state、events、decisions、risks、files、checkpoint。
2. 清空聊天上下文。
3. Agent B 只能调用 `resume_work` 或 `/api/agent/tasks/{id}/handoff`。
4. Agent B 输出恢复结果和下一步行动计划。

指标：

| 指标 | 含义 |
| --- | --- |
| `goalRecovery` | 当前目标恢复是否正确 |
| `doneRecovery` | 已完成事项恢复率 |
| `nextStepRecovery` | 下一步恢复率 |
| `decisionRecovery` | 关键决策恢复率 |
| `riskRecovery` | 风险/约束恢复率 |
| `fileRecovery` | 涉及文件恢复率 |
| `wrongAssumptionRate` | 捏造或误解项目状态的比例 |
| `handoffActionability` | 恢复内容是否能直接指导下一步 |

合格线：

- 核心字段平均恢复率 >= 90%。
- `wrongAssumptionRate` 接近 0。
- agent 不需要用户重新解释项目背景。

## 3. Task Continuation Lift

问题：接入 memory 后，agent 是否真的更能继续完成任务。

测试方式：

为同一批任务分别运行 baseline 和 `second_brain_protocol`：

1. 代码继续任务：另一个 agent 接手未完成实现。
2. 调试任务：根据之前失败、决策和日志继续修复。
3. 文档/架构任务：沿用之前的取舍，不重新发散。
4. 隐私任务：需要读取部分上下文，但不应越权。

指标：

| 指标 | 含义 |
| --- | --- |
| `continuationSuccessRate` | 接手后任务完成率 |
| `turnsToCompletion` | 完成任务所需交互轮数 |
| `timeToFirstUsefulAction` | 第一次有用行动前耗时 |
| `clarificationRate` | 需要向用户澄清的比例 |
| `duplicateWorkRate` | 重复已完成工作的比例 |
| `wrongFileEditRate` | 修改错误文件或方向跑偏的比例 |
| `regressionRate` | 破坏既有测试或约束的比例 |

最重要报告项：

```text
Continuation Success Lift
Clarification Reduction
Duplicate Work Reduction
Wrong File Edit Reduction
```

这些指标比“检索准确率”更能说明系统有用。

## 4. Context Utility

问题：ContextPack 返回的上下文是不是刚好有用，而不是把噪音塞给 agent。

测试方式：

对每个查询标注：

- 必须返回的 critical refs。
- 禁止返回的 forbidden refs。
- 可以返回但不是关键的 optional refs。
- 最大预算。

指标：

| 指标 | 含义 |
| --- | --- |
| `criticalRecall@K` | 关键上下文召回 |
| `contextPrecision@K` | 返回内容中真正相关的比例 |
| `citationCoverage` | 关键内容是否都有 citation |
| `citationUsageRate` | agent 最终输出是否实际使用 citation |
| `noiseRate` | 无关上下文占比 |
| `budgetWasteRate` | 预算被低价值内容消耗的比例 |
| `missingCriticalContextRate` | 漏掉关键上下文的比例 |
| `selectionTraceCoverage` | 是否解释了选择、过滤、截断原因 |

合格线：

- critical refs 不能漏。
- private/profile/task-scoped forbidden refs 不能返回。
- ContextPack 必须遵守 `maxChars`。
- 重要内容必须能追溯到 `citationRefs` 或 `source:` excerpt。

## 5. Memory Write Quality

问题：agent 提出的长期记忆候选是否真的值得保存。

测试方式：

让 agent 在任务后调用 `propose_memory`，然后由用户或规则化 evaluator 判断 proposal 质量。

指标：

| 指标 | 含义 |
| --- | --- |
| `proposalAcceptanceRate` | 候选被接受的比例 |
| `proposalEditDistance` | 接受前需要修改多少 |
| `evidenceCoverage` | proposal 是否带足 evidence refs |
| `duplicateProposalRate` | 是否重复已有记忆 |
| `falseMemoryRate` | 是否编造或过度总结 |
| `wrongStoreRate` | 是否投错 target store |
| `staleMemoryRate` | 是否把已失效信息重新提出 |

合格线：

- agent 只能提出 pending proposal。
- proposal 必须带 evidence refs 或明确说明缺证据。
- 用户接受率、修改量和重复率要作为长期趋势观察。

## 6. Safety Boundary

问题：系统是否在 agent 接入后仍然守住记忆边界。

指标：

| 指标 | 含义 |
| --- | --- |
| `privacyLeakRate` | 默认档泄露 private/profile/sensitive 内容的比例 |
| `taskScopeLeakRate` | 任务作用域串线比例 |
| `unauthorizedWriteBlockedRate` | 未授权写入是否被拒绝 |
| `directLongTermWriteExposure` | agent 工具面是否暴露直接长期记忆写入 |
| `auditCoverage` | agent 读写是否都有 provenance |
| `sourceExcerptDiscipline` | 是否只能按显式 ref 读取原始证据摘录 |

硬门槛：

- `privacyLeakRate` 必须为 0。
- `directLongTermWriteExposure` 必须为 false。
- 所有 agent write 都必须留下 provenance。

## 证据等级

项目展示时不要只说“我们有 eval”，要说明证据等级。

| 等级 | 名称 | 说明 | 简历可信度 |
| --- | --- | --- | --- |
| Tier 0 | Demo Evidence | 手动演示能跑 | 弱，只能证明有界面 |
| Tier 1 | Deterministic Internal Eval | 固定 fixture、无 LLM 调用、可复现 | 中，适合说明设计严谨 |
| Tier 2 | Paired Baseline Eval | 同任务对比 no_memory/readme_only/chat_summary_only | 强，能证明实际增益 |
| Tier 3 | Real Agent Runs | 接入 Codex/Claude/OpenCLI 的真实任务日志 | 很强，能说明真实使用价值 |
| Tier 4 | External/Public Benchmark | 公开数据集或第三方评测 | 最高，但不是近期必需 |

近期目标是 Tier 2；Tier 3 作为加分项。

## 建议新增评估脚本

后续实现时新增：

```powershell
python evals/run_agent_usefulness_eval.py --output evals/reports/agent_usefulness_latest.md --json-output evals/reports/agent_usefulness_latest.json
```

建议输出：

```text
Agent Usefulness Evaluation Report
- Evidence Tier: paired_baseline_internal
- Protocol Usability: 92%
- Handoff Recovery: 94%
- Continuation Success Lift: +28%
- Clarification Reduction: -35%
- Duplicate Work Reduction: -40%
- Context Utility: 84%
- Proposal Quality: 76%
- Safety Boundary: 100%
- Privacy Leak Rate: 0.0%
```

脚本结构：

```text
evals/agent_usefulness/
  cases/
    onboarding_cases.jsonl
    handoff_cases.jsonl
    continuation_cases.jsonl
    context_utility_cases.jsonl
    proposal_quality_cases.jsonl
    safety_cases.jsonl
  runner.py
  baselines.py
  scoring.py
```

不要把它塞进现有 `run_memory_eval.py`，否则评测脚本会继续膨胀。

## Case 设计

### Handoff Case

每个 case 包含：

```json
{
  "id": "handoff-refactor-001",
  "taskGoal": "重构检索 provider，并保持现有测试通过",
  "agentAEvents": [
    "已新增 providers.py",
    "决定保留 LocalSparseVectorProvider 作为默认本地召回",
    "下一步需要更新 retrieval ablation"
  ],
  "expectedRecovery": {
    "goal": ["重构检索 provider"],
    "done": ["新增 providers.py"],
    "decisions": ["保留 LocalSparseVectorProvider"],
    "nextSteps": ["更新 retrieval ablation"]
  }
}
```

### Continuation Case

每个 case 包含：

```json
{
  "id": "continuation-debug-001",
  "baselinePrompt": "继续修复测试失败",
  "memoryState": "包含失败测试、已尝试方案、不能改动的文件、下一步建议",
  "successCriteria": [
    "定位正确模块",
    "不重复已失败方案",
    "测试通过",
    "不修改无关文件"
  ]
}
```

### Context Utility Case

每个 case 包含：

```json
{
  "id": "context-scope-001",
  "query": "继续上一个 agent 的检索重构",
  "requiredRefs": ["task:<id>", "task-digest:<id>", "item:<id>"],
  "forbiddenRefs": ["source:<private-id>"],
  "maxChars": 4000
}
```

## 面试表达

不要说：

> 我做了一个 second brain，可以给 agent 记忆。

要说：

> 我评估的是 agent 接入后是否真的提升任务连续性。通过 paired baseline，我比较 no_memory、README-only、普通摘要和 second brain protocol，在跨 agent 接力任务里衡量 handoff recovery、continuation lift、duplicate work reduction、context utility 和 privacy leak rate。

最有价值的简历句式：

> 构建 Agent Usefulness Evaluation，用 paired baseline 验证本地 memory protocol 的实际增益：衡量跨 agent 状态恢复、任务继续成功率提升、重复工作下降、ContextPack 有用率、proposal 质量和隐私边界，而不是只报告检索命中率。

## 与现有评测的关系

现有 `docs/MEMORY_EVALUATION_PROTOCOL.md` 主要证明 memory 系统内部能力：

- retrieval 是否找得到。
- handoff 字段是否恢复。
- privacy/scope 是否隔离。
- review lifecycle 是否守住。
- evaluator 是否能抓坏结果。

本文件更进一步，证明外部 agent 接入后的实际工作收益：

- agent 是否容易接入。
- agent 是否真的接得上另一个 agent。
- agent 是否更快完成任务。
- agent 是否更少重复、误改、问人。
- agent 写入的记忆是否值得保留。

两者关系：

```text
Memory Evaluation = 系统内部是否正确
Agent Usefulness Evaluation = 接入 agent 后是否真的有用
```

## 近期落地顺序

1. 在现有 evals 外新增 `run_agent_usefulness_eval.py` 的 skeleton。
2. 先实现 deterministic handoff recovery 和 protocol usability。
3. 再实现 paired baseline 的 continuation cases。
4. 把 ContextPack utility 接到 Phase 2 的 `selectionTrace`。
5. 最后用真实 Codex/Claude/OpenCLI 日志做 Tier 3 证据。

不要一开始就追求真实 LLM 自动跑完整 benchmark。先用 deterministic cases 和小规模人工标注，把指标定义牢。
