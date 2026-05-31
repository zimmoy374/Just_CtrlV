# second brain Agent 接力说明

<!-- second-brain:start -->
## second brain 接力入口

进入这个仓库后，先读取当前工作状态：

```powershell
python second_brain.py resume
```

需要确认本地状态是否健康时：

```powershell
python second_brain.py doctor --json
```

没有活跃工作时创建：

```powershell
python second_brain.py start --goal "用户让你完成的目标" --agent "你的 agent 名称"
```

工作中每完成一个有意义的阶段，记录进度：

```powershell
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步" --file "改动文件" --agent "你的 agent 名称"
```

交给另一个 agent 前保存阶段快照：

```powershell
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
```

原则：

- `resume` 是接手工作的入口。
- `doctor` 是诊断数据库、工作区绑定和活跃任务的入口。
- `note` 只记录工作状态，不写正式长期记忆。
- 默认 capability profile 是 `work`；需要读取 profile/private/sensitive 内容时必须显式声明。
- 正式长期记忆只能通过记忆审查台接受待审记忆后进入。
- 不要直接读取或修改 `.data/second_brain.sqlite`。
<!-- second-brain:end -->
