# Paper Lab

在 Codex 里用四个独立视角深读论文，保存一份可以质疑、核验证据和持续讨论的 mental model。
中文解释，保留英文术语、原始标题、公式与必要原文；第一版默认完整 council。

当前保留旧版 council 工具与协议，正在重新设计为内置 PDF 阅读、Specialist 对话和可选检查流程。
论文分析与旧版实跑验收记录已移除。以下命令描述旧版工具，不代表新阅读 UI 已实现。

## 在 Codex 中使用

打开此仓库，直接说：

- `阅读 Megatron-LM，运行完整 council。`
- `继续 Megatron-LM。为什么第一个 GEMM 用 column parallelism？`
- `探索最近两年的 LLM inference scheduling，同时补上经典工作。`
- `给这篇论文设计一个最小实验，让核心机制变得具体。`

仓库 AGENTS.md 路由到 `.agents/skills/paper-council` 和 `paper-discovery`。
如果当前任务尚未刷新技能列表，AGENTS.md 仍提供直接文件入口；也可新开任务。
Skills 规定 protocol，Codex subagents 执行 reasoning，Python 处理确定性操作。
脚本本身不会调用模型或自动生成论文分析，不需要额外的模型 API key。

## 安装

需要 Python 3.11+ 与 Poppler（pdftotext、pdfinfo、pdftoppm）。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# macOS: brew install poppler
# Ubuntu: sudo apt-get install poppler-utils
```

若使用 uv：`uv venv .venv`，然后 `uv pip install --python .venv/bin/python -r requirements.txt`。
网络不可用时解析/下载会显式失败；可使用已核验元数据与用户提供的 PDF。

## 确定性工具

下面是 Codex 可调用的辅助命令，不要求用户日常操作 CLI：

```bash
.venv/bin/python scripts/resolve_paper.py '1909.08053v4' --output .cache/metadata.yaml
.venv/bin/python scripts/download_paper.py .cache/metadata.yaml
.venv/bin/python scripts/create_workspace.py .cache/metadata.yaml --slug megatron-lm-2019 --status reading
.venv/bin/python scripts/resume_paper.py megatron-lm-2019
.venv/bin/python scripts/validate_state.py --require-cache
.venv/bin/python -m unittest discover -s tests -v
```

标题查询返回候选，核对作者/年份/venue 后选择，不能把 string similarity 当匹配概率。
arXiv 从官方 citation metadata 解析并固定版本；DOI 通过 Crossref 解析，arXiv-issued DOI
会回到 arXiv。普通 URL 支持 citation metadata；无此字段时由 agent 查官方来源补齐。
Crossref 不保证公开 PDF，agent 优先找 arXiv、作者、会议或 publisher OA 版本。

```bash
# 备用公开版本需要说明来源；不绕过登录或 paywall
.venv/bin/python scripts/download_paper.py .cache/metadata.yaml --pdf-url 'https://example.org/paper.pdf' --access-basis 'author manuscript'
# 使用本机已有的合法副本
.venv/bin/python scripts/download_paper.py .cache/metadata.yaml --local-pdf /absolute/path/paper.pdf
```

脚本检查 PDF 内容、页数、文本提取和 SHA256，不以扩展名代替检查。扫描件无法提取时
显式停止，OCR 不是本版自动能力。公式/图表必须回看渲染页。已有版本不静默覆盖；
换版需要保留旧状态、逐条重新核验 evidence。DOI 与 arXiv 别名可去重，但两个 provider
没有声明的身份关联仍需人工核对并补 aliases，不能仅凭相似标题自动合并。

## Council 与长期状态

`resolve → cache → workspace → 4 blind reviews → issue-based cross-review → moderator → scheme`

mechanism、systems、evidence、adversarial 四个 reviewer 使用新上下文，只接收原文、
角色、reader profile，分别写 memo。并发不足时分批，全部完成后才共享结果。
这是共享文件系统中的协议隔离，不是权限级沙箱；不能保证不同角色没有模型共同偏差。
默认一轮交叉审查，必要时第二轮，保留争议。只有主代理分配 C/I/P ID 和写正式状态。

```text
profile/reader.yaml          未评估知识用 unknown，不复制示例等级
library/index.yaml          内部阅读索引，非 Zotero 替代品
library/reading_queue.yaml  已选论文及依赖，允许空队列
papers/<slug>/source.yaml   身份、固定版本、PDF hash、相对缓存路径
             claims.yaml   SOURCE / DERIVED / SPECULATION + evidence
             issues.yaml   争议立场、处理理由与剩余不确定性
             scheme.md     面向阅读的 mental model，引用 C/I/P
             prerequisites.yaml / open_questions.md / reading_log.md
             run.yaml      可恢复阶段与 reviewer provenance
             debates/      原始独立 memo、交叉审查记录
discovery/topics.yaml       搜索主题和报告入口
.cache/papers/             PDF、逐页文本、渲染中间文件（不进 Git）
```

继续讨论默认加载 canonical state，不加载全部历史 debates。只有讨论改变了判断、
争议或先修需求才更新状态，并记录原因。`CONFIRMED` 只确认 statement 所限定的范围；
作者报告不等于独立复现，多数同意不等于证据。confidence 为等级+理由，不伪造概率。
校验器检查结构、引用和 hash，不能替代人工核验“引用的页面是否真支持判断”。

## Git 与 GitHub

Git 仅保存代码、通用协议和空的初始化模板，不保存用户论文分析、对话或阅读记录。
旧版脚本仍使用仓库内路径；新版本将支持用户指定的独立数据目录，目前尚未实现。
在新数据目录接口完成前，不运行真实论文工作流。测试数据目录由用户另行指定。
远端为 `git@github.com:chai-yinfeng/paper-lab.git`。

## MVP 边界

不含 Web UI、向量库、Zotero storage parser、自动 OCR、自动全量复现或预读/深读混合模式。
Discovery 由技能配合可用 web tools 完成，不宣称覆盖整个领域；所有近期结论附检索日期。
旧版真实论文产出与验收记录已从发布历史移除。
