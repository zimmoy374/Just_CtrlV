# Just Ctrl+V

一个围绕粘贴设计的本地信息桌面。把文本、链接或图片复制后直接按 `Ctrl+V`，内容会成为当天的卡片，并自动生成简短摘要和关键词。

## 能做什么

- 粘贴文本、网页链接、PNG、JPEG 和 WebP 图片。
- 自动识别内容类型并创建对应卡片。
- 自动提炼摘要和关键词，失败后可以重试。
- 按日期保存卡片，日历只开放今天和已有内容的历史日期。
- 在固定页面内自由拖动卡片，不需要管理无限画布。
- 双击空白处补充文本，双击图片查看大图。
- 每天使用稳定但不同的手绘角落装饰。
- 所有卡片和图片默认保存在本机 `.data/`。

## 安装

需要 Python 和 Node.js。在项目根目录运行：

```powershell
python install.py
```

然后在 `.env` 中配置兼容 OpenAI Chat Completions 的模型：

```text
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=支持图片输入的模型
JUST_CTRLV_DATA_DIR=.data
```

## 运行

```powershell
python run.py
```

应用会打开 `http://127.0.0.1:5173`。

## 验证

```powershell
python -m pytest -q
cd client
npm run lint
npm run test:smoke
npm run build
```
