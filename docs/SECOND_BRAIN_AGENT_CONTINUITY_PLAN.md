# second brain 跨 Agent 记忆闭环计划

## 目标体验

用户在一个 agent 里工作后，换到另一个 agent 时不需要复述背景。新 agent 进入项目后，先调用 `python second_brain.py resume` 或 MCP `resume_work`，即可恢复当前目标、进度、关键决策、风险、下一步和必要引用，然后继续把状态写回 `second brain`。

这不是前端任务工作台，也不是让用户管理 agent 日志。它是 agent 协议层的工作状态恢复能力。

当前版已经明确：记忆审查台只处理长期记忆审查，不展示或返回 task capsule、agent read 面板。任务接力和 agent 读写审计分别走 CLI/MCP、`/api/agent/*`、`/api/system/status` 和导出包。

## 设计来源

- TencentDB Agent Memory：借鉴分层记忆、自动提炼、上下文卸载。只借鉴方法，不照搬自动写入长期记忆；正式长期记忆仍需用户审查。
- Claude Code / Codex：借鉴项目入口文件、上下文压缩和恢复思路。项目内保留 `AGENTS.md`、`CLAUDE.md` 等可发现入口。
- CLI-Anything / OpenCLI：借鉴 agent-native CLI、稳定 JSON 输出和自动注册体验。CLI 是基础入口，MCP 和 skill 是外壳。

## 分层记忆

- L0 原始证据层：`SourceItem`、`TaskEvent`、用户原始输入。它们是用户资产，不被摘要替换，不因压缩删除。
- L1 工作状态层：`TaskState`、`TaskCheckpoint`、`TaskDigest`、`HandoffPack`。它们给 agent 恢复当前工作，不直接进入长期知识库。
- L2 审查知识层：`KnowledgeItem`、`KnowledgePage`、规则、流程经验。只有用户确认或审查接受后才进入正式知识。
- L3 动态事实层：profile facts、relations、conflicts、supersession、invalidation。用于处理会变化的事实。

## 压缩原则

- 压缩只发生在上下文投影层，不替换 L0 原始证据。
- 工作事件多起来后，较早事件被汇总进 `TaskDigest`，handoff 默认返回滚动摘要、当前状态、最近事件和 refs。
- agent 需要细节时，按 ref 再读取具体 task event、checkpoint 或 source excerpt。
- `ContextPack` 默认按预算读取：协议提醒 -> 当前任务摘要 -> 规则/流程 -> 动态事实 -> 相关知识 -> 必要证据摘录。

## 接入路径

- CLI：`second_brain.py start/resume/note/checkpoint/healthcheck/doctor/tools/capabilities/demo/install-agent`。
- MCP：`resume_work`、`record_progress`、`checkpoint_work`、`search_memory`、`read_evidence`、`propose_memory`。
- 入口文件：`AGENTS.md` 给 Codex 和通用 agent，`CLAUDE.md` 给 Claude Code，OpenCLI 描述文件给支持工具发现的 agent。

## 权限档位

`capabilityProfile` 是本地 agent 读取档位，不是网络鉴权系统。它的作用是避免外部 agent 因参数误用读到过多内容：

- `work`：默认档位，只读普通工作上下文。
- `profile`：允许读取用户确认过的 profile fact。
- `private`：允许读取 private 证据摘录。
- `sensitive`：允许读取 private 和 sensitive 证据摘录。
- `trusted`：允许读取所有本地 agent capability，但仍不能直接写正式长期记忆。

CLI 用 `python second_brain.py capabilities --json` 查看档位；API 用 `GET /api/agent/capabilities`；MCP 的 `search_memory` 和 `read_evidence` 也接受 `capabilityProfile`。

## 状态机与诊断

- `TaskSession` 状态切换只走 `tasks/state_machine.py`。
- `/api/tasks/*` 和 `/api/agent/tasks/*` 的写入都必须经过终态保护。
- 终态任务不能继续写入进展、状态或 checkpoint；继续工作时创建新任务。
- `python second_brain.py doctor --json` 和 `GET /api/system/status` 用于快速判断当前工作区是否能接力、后台任务是否卡住、待审记忆是否堆积。

## 自动记录

- 支持 hooks 的 agent 可以在每轮结束、停止前、压缩前写入阶段摘要。
- 不支持 hooks 的 agent 通过入口文件和 MCP 工具说明执行同一协议。
- 不记录每条 shell 输出，只记录有意义的阶段变化。
- 写入前做长度限制、敏感字段过滤和 refs 绑定。

## 验收标准

- 当前 agent 记录状态后，另一个 agent 只运行 `python second_brain.py resume` 或 MCP `resume_work` 就能继续。
- 多个项目不会互相抢同一个活跃任务。
- 大量事件存在时，resume 仍返回压缩后的可读 handoff。
- agent 不能绕过审查门直接写入正式长期记忆。
- `doctor` 能告诉用户当前数据库、工作区绑定、活跃任务和后台任务是否健康。
- 私密读取必须通过 capability profile；默认接力不会暴露 private/profile/sensitive 记忆。
- `/api/review/workbench` 不返回任务工作状态或 agent 读取列表，避免把协议运行态混进用户长期知识审查。
