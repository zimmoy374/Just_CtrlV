# second brain

一个本地优先的 Agent Memory Core。它把用户拥有的原始证据保存为可审计资产，把经过审查的内容沉淀成长期记忆，并通过有预算、有引用、有权限边界的 ContextPack 给外部 agent 接力使用。

项目重点不是做更多页面，而是证明 agent 接入后能更可靠地恢复任务状态、读取相关上下文、提交待审记忆，并用可复现评测说明它不是玩具 demo。

## 安装

先安装 Node.js 和 Python，然后在项目根目录运行一次：

```powershell
python install.py
```

打开 `.env`，填写 OpenAI 或同协议模型接口：

```text
OPENAI_API_KEY=sk-你的密钥
OPENAI_BASE_URL=https://你的中转地址/v1
OPENAI_MODEL=支持识图的模型名
SECOND_BRAIN_DATA_DIR=.data
```

## 运行

双击 `run.py`，或运行：

```powershell
python run.py
```

应用会自动打开浏览器页面：`http://127.0.0.1:5173`

## 使用

- Capture Inbox：保存文本、链接和图片证据；截图后回到页面按 `Ctrl+V` 可以粘贴成证据卡片。
- Search & Context：搜索经过审查的长期记忆，查看命中原因、局部结果解释、ContextPack 和 selection trace。
- Review Gate：审查待审记忆、证据权限、事实冲突和导出包。
- Agent Handoff：外部 agent 进入项目后先 `resume`，阶段完成时静默 `note --quiet`，换 agent 或收尾时保存 checkpoint。

## 知识库

- 统一检索入口是 `/api/knowledge/search`，当前会搜索正式 KnowledgeItem。
- 检索层采用本地优先的 hybrid pipeline：SQLite FTS/字段匹配召回、本地 deterministic vector 召回、RRF 融合和轻量重排；外部向量库或云 embedding 可以后续替换 provider。
- 搜索页会基于当次搜索结果自动生成局部关联网络，不维护单独的全库关系入口。
- 外部 agent 先读取 `/api/agent` 或 `/api/agent/instructions`，再读取 `/api/agent/tools`，然后通过 `/api/agent/context?q=...` 按预算获取 ContextPack；`selectionTrace` 会说明选中、过滤、去重和截断原因，它不需要也不应该全量读取知识库。
- 外部 AI 已经让用户预览并确认的整理结果，可以通过 `/api/knowledge/import-confirmed` 写入正式知识库。
- 记忆审查台只处理待审记忆、个人事实、冲突、规则、流程经验、知识页和原始证据；任务接力状态不会混进这个页面。
- 用户卸载或迁移前，可以调用 `/api/knowledge/export` 导出 SourceItem、KnowledgeItem、KnowledgePage、MemoryProposal、外部 agent 协议记录和 provenance。

## 跨 agent 接力

进入项目后，agent 应先运行：

```powershell
python second_brain.py resume
```

常用命令：

```powershell
python second_brain.py start --goal "当前目标" --agent "agent 名称"
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步"
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
python second_brain.py doctor --json
python second_brain.py capabilities --json
python second_brain.py demo
python second_brain.py tools --json
python second_brain.py install-agent --target all
```

支持 MCP 的 agent 可以使用本地 stdio server：

```powershell
python second_brain_mcp.py
```

MCP 工具包括 `resume_work`、`record_progress`、`checkpoint_work`、`search_memory`、`read_evidence`、`propose_memory`。其中 `propose_memory` 只创建待审记忆，不会直接写入正式长期记忆。

默认读取档位是 `work`，只用于普通工作接力。需要读取个人资料、私密或敏感证据时，agent 必须显式选择 `capabilityProfile`，并且仍然只能读取预算化 ContextPack 或明确 ref 的证据摘录。

## 架构约定

- 当前整体架构说明见 `docs/SECOND_BRAIN_ARCHITECTURE.md`。
- 面试导向的项目收敛和后续实施路线见 `docs/AGENT_MEMORY_KERNEL_ROADMAP.md`。
- 外部 agent 接入后是否真的有用的评估方案见 `docs/AGENT_USEFULNESS_EVALUATION.md`。
- 记忆评测协议见 `docs/MEMORY_EVALUATION_PROTOCOL.md`。
- SourceItem、KnowledgeItem、KnowledgePage、MemoryProposal、MemoryDecision、ProvenanceEvent 和 Profile Temporal Graph 是稳定核心。
- 外部 agent 只能读取受限上下文、读取明确引用的证据摘录、提交待审记忆；不能直接写入长期记忆、覆盖事实、解决冲突或清除证据。
- 任务状态切换集中由状态机处理，`/api/tasks/*` 和 `/api/agent/tasks/*` 都不能绕过终态保护。
- agent 任务状态是协议内部状态，不作为个人知识库前端页面展示。
- agent 读取/写入审计保存在 provenance、系统状态和导出包里，不作为记忆审查台内容。
- 任务滚动摘要只压缩上下文投影，不替换原始 `TaskEvent` 或 `SourceItem`。
- `python second_brain.py doctor --json` 和 `/api/system/status` 是本地诊断入口。

## 开发验证

默认验收方式是不启动本地服务、不跑浏览器，直接跑命令：

```powershell
python -m pytest -q
cd client
npm run lint
npm run test:smoke
npm run build
```

记忆可靠性 challenge 评分台在 `evals/`，用于输出可复现的 ContextPack 检索、selection trace、跨 agent 接力、隐私/作用域隔离、审查门生命周期和 evaluator 故障注入指标；报告会区分功能分、评测严格度、证据等级和公开 benchmark 状态，避免把内部高分误写成 SOTA：

```powershell
python evals/run_memory_eval.py --output evals/reports/latest.md --json-output evals/reports/latest.json
```

本地规模压测独立运行，覆盖 SQLite 数据增长、hybrid retrieval 延迟/QPS、并发读和并发写冲突。它不是生产分布式 QPS 宣称，而是给简历和面试提供可复现实验口径：

```powershell
python evals/run_scale_benchmark.py --sizes 1000 5000 --queries 40 --read-workers 2 --write-workers 2 --writes-per-worker 10 --output evals/reports/scale_latest.md --json-output evals/reports/scale_latest.json
```

外部 agent 接入后是否真的有用，用 Agent Usefulness Eval 做 baseline 对比，衡量接力恢复、任务继续收益、重复工作下降、ContextPack 有用率和安全边界：

```powershell
python evals/run_agent_usefulness_eval.py --output evals/reports/agent_usefulness_latest.md --json-output evals/reports/agent_usefulness_latest.json
```
