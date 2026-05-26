# Just Ctrl V

一个本地使用的 AI 知识采集与整理工具。你可以用 Ctrl+V 保存截图、文本和链接，并把它们沉淀成可搜索、可导出、可给外部 AI 使用的个人知识库。

## 安装

先安装 Node.js 和 Python，然后在项目根目录运行一次：

```powershell
python install.py
```

打开 `.env`，填写 OpenAI 或 OpenAI 兼容接口：

```text
OPENAI_API_KEY=sk-你的密钥
OPENAI_BASE_URL=https://你的中转地址/v1
OPENAI_MODEL=支持识图的模型名
JUST_CTRL_V_DATA_DIR=.data
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

- 产品级统一检索入口是 `/api/knowledge/search`，当前会搜索正式 KnowledgeItem。
- 外部 AI 可以通过 `/api/knowledge/context?q=...` 按预算读取 ContextPack，不需要也不应该全量读取知识库。
- 外部 AI 已经让用户预览并确认的整理结果，可以通过 `/api/knowledge/import-confirmed` 写入正式知识库。
- 用户卸载或迁移前，可以调用 `/api/knowledge/export` 导出 SourceItem、KnowledgeItem、KnowledgePage 和 provenance。
