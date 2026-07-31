# CtrlV

CtrlV 是一个围绕“粘贴”设计的本地信息桌面。复制文本、网页链接或图片后按下 `Ctrl+V`，内容会保存到当天的纸面，并自动生成摘要和关键词。

## 效果展示

![CtrlV 日期白板中的文本卡片、图片卡片与桌面素材](assets/readme/ctrlv-board-showcase.png)

日期白板可以同时组织文本、网页内容、图片与桌面截图，并保留自由排布的视觉空间。

## 功能

- 粘贴文本、网页链接和图片，快速生成白板卡片。
- 在 Windows 中使用 `Ctrl+Shift+X` 截取任意区域并直接贴入白板。
- 自由移动、缩放、编辑和整理内容，并按日期保存白板状态。
- 自动生成内容摘要和关键词，帮助快速理解与分类。
- 按日期浏览历史，通过纸飞机随机回顾过去的内容。
- 数据和上传图片保存在自己的服务器中。

## 技术结构

- 前端：原生 HTML、CSS、JavaScript，无构建步骤
- 后端：FastAPI
- 数据库：SQLite，只有一张 `cards` 表
- 图片：保存在 `.data/uploads/`

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

在 `.env` 中填写兼容 OpenAI Chat Completions API 的服务配置：

```text
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-model
```

启动后访问 `http://127.0.0.1:8765`。

右上角猫爪菜单的齿轮可以启用或关闭全局截图，并直接录入新的快捷键。全局截图助手目前仅在 Windows 的 `run.py` 本地启动方式下运行；直接使用 `uvicorn` 启动时只提供 Web 服务。

## 部署

### 前后端一起部署

FastAPI 会直接托管 `client/` 静态文件。服务器启动命令：

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

部署时需要：

- 将 `.data/` 放在持久化磁盘中
- 通过环境变量提供 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL`
- 不要把 `.env`、`.data/` 或用户上传的图片提交到 GitHub

### 前后端分开部署

`client/` 可以直接上传到 GitHub Pages、Cloudflare Pages、Netlify 或其他静态托管服务。

在 `client/config.js` 中填写后端地址：

```javascript
window.CTRLV_API_BASE = "https://api.example.com"
```

后端通过 `CTRLV_ALLOWED_ORIGINS` 允许前端域名访问：

```text
CTRLV_ALLOWED_ORIGINS=https://example.com,https://www.example.com
```

API 密钥始终只配置在后端，不要写入 `client/config.js`。

## 数据目录

```text
.data/
├── ctrlv.sqlite
└── uploads/
```

可以通过 `CTRLV_DATA_DIR` 修改数据目录。备份 `.data/` 即可备份全部内容。

## 配置

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | AI 服务密钥 | 无 |
| `OPENAI_BASE_URL` | Chat Completions API 地址 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 使用的模型 | `gpt-5.4` |
| `CTRLV_DATA_DIR` | SQLite 和图片目录 | `.data` |
| `CTRLV_ALLOWED_ORIGINS` | 允许跨域访问 API 的前端域名 | 本机地址 |
| `CTRLV_HOST` | `run.py` 监听地址 | `127.0.0.1` |
| `CTRLV_PORT` | `run.py` 监听端口 | `8765` |

## 测试

```powershell
python -m pytest -q
node --check client\src\app.js
```

前端不依赖 npm；这里的 Node 命令只用于检查 JavaScript 语法，不影响运行和部署。
