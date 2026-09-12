# Paper Lab

本地论文阅读工作台：在 PDF 原文旁边讨论原理，选中文字或框选图表提问，手动保存自己的理解。
中文解释，保留必要的 English terms 和公式。应用通过 LLM API 运行，不依赖 Codex 或 ChatGPT 会话。

## 已实现

- 自定义本地工作目录；上传与 arXiv 搜索下载统一导入 `pdfs/`，按 SHA256 去重。
- PDF.js 预览、目录、分页、缩放、文字选择和矩形选区；新回答按物理页码与页内片段引用并回跳，高亮可定位的原文片段。
- 每篇论文多个主题对话，流式回答、停止生成、恢复阅读位置和最近主题。
- 默认 Specialist，一次模型调用；Reader + Checker 显式选择，最多两次调用。
- 原文上下文预览；按当前页、相邻页和词项相关性补充同篇片段，不自动外部搜索。
- 对话自动保存，笔记手动确认、编辑、导出 Markdown。
- DeepSeek 与 OpenAI-compatible provider 接口；默认 `deepseek-flash`（V4.1 Flash）。
- 每次输出上限，usage 按调用步骤记录；失败不自动重试、不自动启动更多 agent。

## 启动

需要 uv、Python 3.11+、Node.js 22.13+ 和 Poppler。macOS 可用
`brew install uv poppler` 安装环境管理器和 PDF 工具。

```bash
uv sync --locked
npm ci
npm run build
uv run --locked python -m paper_lab
```

打开 http://127.0.0.1:8765，在“工作目录与模型”中使用“选择文件夹…”打开 macOS
原生目录选择器；也可以直接输入专用的绝对路径。
未选择目录时，服务不会创建用户数据。目录必须是空目录或已有 Paper Lab 工作目录，且在 Git 仓库之外。

### macOS launcher

构建并安装 menu bar launcher：

```bash
scripts/build-macos-app.sh "$HOME/Applications/Paper Lab.app"
open "$HOME/Applications/Paper Lab.app"
```

启动后，菜单栏中的 Paper Lab 图标可用于打开、启动、停止或重启服务，以及查看
`~/Library/Logs/Paper Lab/server.log`。退出 launcher 会停止由它启动的服务。
launcher 记录构建时的仓库路径；仓库移动后重新运行安装命令即可。
最近打开的有效工作目录记录在
`~/Library/Application Support/Paper Lab/launcher.json`，重启时会自动恢复；
只有已经包含 Paper Lab workspace marker 的目录才会被自动打开。

也可以在启动时明确指定：

```bash
uv run --locked python -m paper_lab --data-dir /absolute/path/my-paper-library
```

目录可通过 `PAPER_LAB_DATA_DIR` 环境变量指定；命令行参数优先。
切换目录需重启服务。将整个工作目录搬迁后，可从新路径重新打开；备份/搬迁前先停止服务。

API key 可以在界面中输入并持久保存在 macOS Keychain，或通过 `DEEPSEEK_API_KEY`
环境变量提供。Keychain 项使用 Paper Lab 独占的 service，并按 provider 与 API 地址分开，
不会与其他应用保存的 DeepSeek key 混淆。它不会写入工作目录、浏览器存储或 Git，也不会从状态接口返回。
未配置 key 时可以阅读 PDF 和管理已有笔记。

DeepSeek 默认关闭 thinking，单次输出上限 4096 tokens；可以在设置中修改。
官方 API ID 为 `deepseek-flash`，不是 `deepseek-v4.1-flash` 或旧版兼容别名。
模型与 provider 可以切换；更换 API 地址时会清空会话 key，避免将旧 key 发往新地址。
兼容 provider 当前使用 Chat Completions 协议，图像能力由设置明确声明；不保证兼容所有厂商扩展。

## 工作目录与代码的边界

```text
用户选择的工作目录/
  workspace.json       目录与 schema 标记
  pdfs/<sha256>.pdf     论文实体；不依赖原始下载文件仍在原位
  library.sqlite3      论文、逐页文字、主题、对话、笔记、usage、设置与进度
  cache/               导入和渲染的临时文件
```

整个目录都是用户数据，不进入 GitHub。用户选区引用包含 PDF hash、页码和归一化坐标；AI 回答还保存页内片段编号，并在解析文本能够匹配 PDF word boxes 时提供片段高亮。
SQLite 是唯一正式记录；导出的 Markdown 是副本，不做双向同步。
API 调用会把选区和相关文本发送到所选 provider；本地保存不意味着模型在本地运行。

```text
paper_lab/             FastAPI、本地数据层、文档处理、上下文、模型接口
web/src/               React 阅读界面与 PDF.js 交互
scripts/prepare-web-assets.mjs   打包 PDF.js 字体/CMap/WASM，不依赖远端 CDN
.agents/skills/         旧版 council/discovery 协议，显式调用时参考
scripts/*.py           旧版 council CLI；不用于新应用的用户数据
```

旧版 council 协议保留，但没有接入新 UI。旧 CLI 使用仓库内路径，不要用它运行新的真实阅读任务。

## 开发与验证

```bash
# 终端一：本地后端（未指定目录时保持未配置状态）
uv run --locked python -m paper_lab
# 终端二：界面开发，/api 自动转发到本地后端
npm run dev

# 无磁盘工作目录、无真实模型的内存测试
uv run --locked python -m unittest discover -s tests -p test_app.py -v
npm run build
```

实际 PDF 导入、图文选区对齐、下载、持久化重启和真实 API 联调，需要用户指定临时工作目录后进行。
目前构建与内存 API 测试通过，不代表上述真实文件流程已经验收。详见 [架构与验证边界](docs/architecture/local-reader.md)。
