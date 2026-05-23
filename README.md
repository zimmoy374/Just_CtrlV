# Just Ctrl V（加入每周结束自动提炼，定期删除机制中...）

一个本地使用的 AI 灵感板。你可以按周保存截图和文本卡片，在画布里自由拖拽排布，并用 AI 自动提炼总结和关键词。

## 安装

先安装 Node.js 和 Python，然后在项目根目录运行一次：

```powershell
python install.py
```

打开 `.env`。如果你用的是 OpenAI 接口兼容的中转，推荐这样填（二选一）：

```text
AI_PROVIDER=openai
OPENAI_API_KEY=sk-你的密钥
OPENAI_BASE_URL=https://你的中转地址/v1
OPENAI_MODEL=支持识图的模型名
INSPIRATION_DATA_DIR=.data
```

也可以继续使用 Gemini：

```text
AI_PROVIDER=gemini
GEMINI_API_KEY=你的密钥
GEMINI_MODEL=gemini-2.5-flash-lite
INSPIRATION_DATA_DIR=.data
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
