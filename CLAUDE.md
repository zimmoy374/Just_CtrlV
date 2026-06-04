# Claude Code 接力说明

<!-- second-brain:start -->
## second brain / Agent Memory Core 接力入口

开始工作前先运行。用户只说“继续”时也应先执行：

```bash
python second_brain.py resume
```

如果接力失败或状态不清楚，运行：

```bash
python second_brain.py doctor --json
```

阶段完成后静默记录，不要每次告诉用户“已记录”：

```bash
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步" --agent "claude-code" --quiet
```

用户说“保存、换 agent、明天继续、先到这”时运行，并只短提示一次：

```bash
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
```

默认运行策略是 `balanced`：平时静默记录，交接节点才短提示。不要把工作事件直接写成正式长期记忆；需要长期保存的内容只能提交为待审记忆。默认 capability profile 是 `work`，不要主动扩大读取范围，除非用户明确要求。
<!-- second-brain:end -->
