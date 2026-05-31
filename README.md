# second brain

一个本地优先的个人知识与记忆系统。你可以保存截图、文本和链接，把它们沉淀成可搜索、可导出、可给外部 agent 按协议读取的 second brain。

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

没有的话：推荐搜推理时代，里面找带'free'并且支持图片输入的模型，直接配置到.env里就能体验。

## 运行

双击 `run.py`，或运行：

```powershell
python run.py
```

应用会自动打开浏览器页面：`http://127.0.0.1:5173`

## 使用

- 双击画布空白处新增文本卡片。
- 截图后回到页面按 `Ctrl+V`，图片会粘贴成卡片。
- 按住画布空白处拖动，可以移动整块画布。
- 双击图片卡片可以放大查看，滚轮缩放，按住图片拖动，点击图片外关闭。
- 点击关键词可复制，悬停关键词可删除。

## 知识库

- 统一检索入口是 `/api/knowledge/search`，当前会搜索正式 KnowledgeItem。
- 搜索页会基于当次搜索结果自动生成局部关联网络，不维护单独的全库关系入口。
- 外部 agent 先读取 `/api/agent` 或 `/api/agent/instructions`，再读取 `/api/agent/tools`，然后通过 `/api/agent/context?q=...` 按预算获取 ContextPack；它不需要也不应该全量读取知识库。
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
- 跨 agent 接力路线见 `docs/SECOND_BRAIN_AGENT_CONTINUITY_PLAN.md`。
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
npm run build
```
