# Claude Code 接力说明

<!-- second-brain:start -->
## second brain 接力入口

开始工作前先运行：

```bash
python second_brain.py resume
```

如果接力失败或状态不清楚，运行：

```bash
python second_brain.py doctor --json
```

阶段完成后运行：

```bash
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步" --agent "claude-code"
```

停止或交接前运行：

```bash
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
```

不要把工作事件直接写成正式长期记忆；需要长期保存的内容只能提交为待审记忆。默认 capability profile 是 `work`，不要主动扩大读取范围，除非用户明确要求。
<!-- second-brain:end -->
