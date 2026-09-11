# Paper Council Repo — Design Brief

## 1. 项目目标

构建一个个人使用的论文深度阅读工作流，主要运行在：

**Codex + Skills + Subagents + 本地持久化状态**

目标不是让 AI 替代用户阅读论文，而是：

> 在用户真正阅读论文之前，由多个独立视角的 agent 对论文进行结构化分析、交叉质疑和收敛，形成一份带有证据、争议、知识缺口和阅读建议的 mental model；随后用户可以围绕这个模型持续讨论，而不会因为聊天上下文增长而逐渐偏离论文核心。

这个 repo 主要解决几个问题：

1. 普通 AI summary 会隐藏重要算法和工程细节。
2. 单个 LLM 很容易沿用论文作者自己的 narrative，而不是重新审视设计。
3. 用户自身知识存在不均匀的 gap，需要根据已有能力动态补 prerequisite。
4. 长对话会产生 context drift，不能把聊天记录当长期状态。
5. 阅读论文不能完全脱离实践，需要能够指出值得实现、复现或验证的部分。
6. 论文来源目前主要通过 Zotero 管理，但不希望依赖 Zotero 内部随机编码的 PDF 文件目录。
7. 系统还应支持从一个主题出发探索近期/经典工作并建立候选阅读列表。

---

# 2. 总体原则

整个系统按照三层设计：

```text
Skill
    ↓
定义阅读 protocol、agent 职责、讨论和收敛规则

Subagents
    ↓
执行独立阅读、critic、cross-review、teaching 等工作

Persistent Paper State
    ↓
保存已经形成的论文理解，而不是依赖 chat history
```

其中：

```text
Skill = protocol
Subagents = reasoning workers
Local files = canonical memory
Chat = interaction layer
```

**聊天历史永远不是论文理解的 source of truth。**

长期状态必须写入 repo。

---

# 3. Zotero 和本项目的边界

Zotero 继续负责：

* bibliography
* citation
* collection
* tag
* 日常论文收藏
* 用户现有 PDF 管理

Paper Council 不试图替代 Zotero，也不直接依赖 Zotero 的随机文件目录。

用户向 Codex 输入：

```text
Read "Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism"
```

系统应该自行完成：

```text
论文标题
 ↓
metadata resolution
 ↓
DOI / arXiv ID / canonical URL
 ↓
找到合法可访问 PDF
 ↓
下载到 Paper Council 自己的 local cache
 ↓
创建 paper workspace
```

因此 Paper Council 自己只维护一份**工作缓存**。

PDF 不需要进入 git。

建议：

```text
.cache/papers/
    1909.08053.pdf
    1701.06538.pdf
```

而论文分析状态进入：

```text
papers/
    megatron-lm-2019/
    sparsely-gated-moe-2017/
```

`.gitignore` 忽略：

```text
.cache/
*.pdf
```

这样：

* Zotero 仍是正式文献库；
* Paper Council 有自己稳定、可预测的本地 PDF cache；
* Git 只追踪真正有价值的知识状态；
* 不需要解析 Zotero 那套随机目录。

未来可以增加 Zotero adapter，但不是 MVP 的 dependency。

---

# 4. Repo 建议结构

```text
paper-council/
│
├── AGENTS.md
├── README.md
│
├── profile/
│   └── reader.yaml
│
├── library/
│   ├── index.yaml
│   └── reading_queue.yaml
│
├── papers/
│   └── <paper-slug>/
│       ├── source.yaml
│       ├── scheme.md
│       ├── claims.yaml
│       ├── open_questions.md
│       ├── prerequisites.yaml
│       ├── reading_log.md
│       │
│       └── debates/
│           ├── initial-review.md
│           ├── round-01.md
│           └── ...
│
├── discovery/
│   ├── topics.yaml
│   └── reports/
│
├── scripts/
│   ├── resolve_paper.py
│   ├── download_paper.py
│   ├── create_workspace.py
│   └── ...
│
├── .cache/
│   └── papers/
│
└── .codex/
    └── skills/
        ├── paper-council/
        │   ├── SKILL.md
        │   └── references/
        │       ├── roles.md
        │       ├── debate-protocol.md
        │       ├── state-schema.md
        │       └── teaching-protocol.md
        │
        └── paper-discovery/
            ├── SKILL.md
            └── references/
```

其中 `paper-council` 和 `paper-discovery` 最好最终做成两个 Skill。

它们共享同一个 library 和 paper workspace，但属于两个完全不同的 workflow。

---

# 5. Paper identity 与下载

不能使用标题字符串本身作为论文唯一身份。

每篇论文应该解析出：

```yaml
title:
authors:
year:

doi:
arxiv_id:

canonical_url:
pdf_url:

paper_id:
slug:

retrieved_at:
source:
```

paper ID 优先级可以是：

```text
arxiv:<id>
doi:<doi>
fallback:<normalized-title-hash>
```

例如：

```yaml
paper_id: arxiv:1909.08053
slug: megatron-lm-2019
```

论文获取逻辑应该是：

```text
title / DOI / arXiv / URL
        ↓
resolve metadata
        ↓
identity matching
        ↓
locate accessible PDF
        ↓
cache
```

PDF source 优先考虑：

```text
arXiv
→ 作者/实验室公开版本
→ conference proceedings
→ publisher open-access version
```

不尝试绕过登录、paywall 或访问控制。

如果标题匹配存在歧义，resolver 返回多个 candidate，并显示：

```text
title
authors
year
venue
DOI/arXiv
matching confidence
```

---

# 6. 一篇论文的 canonical state

## scheme.md

这是整个项目最重要的文件。

它不是 summary，也不应该复刻：

```text
Introduction
Method
Experiments
Conclusion
```

而应该重构论文：

```markdown
# Problem

# Core Thesis

# Mental Model

# Architecture / Algorithm

# Key Design Decisions

## D1
## D2
## D3

# Assumptions

## A1
## A2

# Claim → Evidence Map

# Engineering Implications

# Alternatives

# Disputed Issues

# Prerequisite Gaps

# Reproduction Opportunities

# What I Should Read Carefully

# What Can Be Skimmed

# Open Questions
```

`scheme.md` 表达的是：

> 用户最终应该在脑中建立怎样一个关于这篇论文的 object model。

而不是论文写了什么章节。

---

# 7. Claim system

所有重要判断应该有稳定 ID，例如：

```text
C1
C2
C3
...
```

`claims.yaml`：

```yaml
- id: C17

  statement:
    Expert balancing is encouraged by the training objective
    but is not guaranteed by runtime routing.

  type: derived

  evidence:
    - section: "3.2"
      equation: 7

    - section: "3.3"
      algorithm: 1

  confidence: 0.84

  status: confirmed
```

claim 类型至少区分：

```text
SOURCE
论文明确说了什么

DERIVED
从论文内容能够合理推导什么

SPECULATION
agent 提出的可能解释或假设
```

绝不能混在一起。

---

# 8. Evidence-first

任何非平凡技术 claim 都应该尽量附带 locator：

```text
section
page
equation
figure
table
algorithm
appendix
```

例如：

```text
C12
SOURCE
The auxiliary loss encourages load balancing.

Evidence:
§2.4, Eq. 5
```

不能只输出：

> “论文证明了……”

而不给用户回到论文原文验证的位置。

---

# 9. Multi-agent 初始阅读

论文首次进入系统后，执行：

## Phase 1 — Blind Independent Review

默认至少四个独立 agent：

### Mechanism / Algorithm Agent

负责重新建立：

```text
problem
mathematical formulation
algorithm
dataflow
optimization objective
assumptions
```

重点不是解释作者说了什么，而是：

> 如果没有作者 narrative，自己会如何重建这个方法？

---

### Systems / Implementation Agent

重点寻找：

```text
真实实现需要哪些组件？
论文遗漏了哪些 implementation details？
memory / compute / communication cost 是什么？
有哪些隐含 runtime assumptions？
哪些地方工程上可能很难成立？
```

对于 AI Systems 论文尤其重要。

---

### Evidence Auditor

建立：

```text
claim → evidence
```

特别检查：

```text
哪个实验真正支持哪个 claim？
有没有 claim 没被 isolate？
有没有同时改变多个变量的 ablation？
baseline 是否公平？
metric 是否真的回答问题？
```

---

### Adversarial Reviewer

主动抵抗作者 framing。

每一个 major design decision 都问：

```text
为什么一定这样设计？

有没有合理 alternative？

论文有没有证明 alternative 不行？

当前 evidence 能区分这些解释吗？

有没有隐藏 assumption？
```

其目标不是“找茬”，而是产生**independent hypothesis**。

---

# 10. 第一轮 Agent 必须隔离

最重要的规则之一：

> Blind pass 阶段，agent 不允许读取其他 agent 的结果。

即：

```text
                   PAPER
                     │
        ┌────────────┼────────────┐
        ↓            ↓            ↓
 Algorithm        Systems       Evidence
        ↓            ↓            ↓
     Memo A        Memo B       Memo C

               Adversarial
                   ↓
                Memo D
```

每个 agent 初始只接收：

```text
paper
role
reader profile
```

这样尽量降低：

```text
anchoring
groupthink
shared narrative bias
```

---

# 11. 不进行自由聊天式 Multi-Agent Debate

第二阶段不是：

```text
Agent A:
我觉得……

Agent B:
我同意，而且……

Agent C:
补充一点……
```

这种形式非常容易快速形成假共识。

应该把冲突转换成结构化 **Issue**。

例如：

```text
C17

Algorithm Agent:
routing objective assumes approximate balance
```

Systems agent 创建：

```text
O17-A

Objection:
runtime capacity still imposes independent constraints
```

Evidence agent：

```text
O17-B

Neither interpretation is experimentally isolated.
```

然后形成：

```yaml
issue: I17

related_claims:
  - C17

positions:
  - algorithm
  - systems
  - evidence

status: disputed
```

---

# 12. Moderator

只有完成 cross-review 后，Moderator 才执行。

Moderator 不要求强制共识。

每个 issue 可以被标记：

```text
CONFIRMED

DISPUTED

OPEN

REJECTED
```

例如：

```markdown
## I17 — Expert balancing

Status: DISPUTED

Current synthesis:

Training encourages balanced routing, but runtime
capacity remains an independent constraint.

Evidence:

- Eq. 7
- Algorithm 1
- Table 4

Remaining uncertainty:

The paper does not isolate auxiliary balancing loss
while holding capacity factor constant.
```

**保留 disagreement 是 feature，不是 failure。**

---

# 13. Reader Model

系统维护：

```text
profile/reader.yaml
```

例如：

```yaml
probability:
  level: 2

optimization:
  level: 2

deep_learning:
  level: 3

transformers:
  level: 4

llm_inference:
  level: 4

cuda:
  level: 3

distributed_systems:
  level: 3

distributed_training:
  level: 2

networking:
  level: 1
```

level 含义：

```text
0 = unfamiliar

1 = recognize the concept

2 = understand with explanation

3 = independently derive / implement

4 = critique / modify / design
```

注意：

Reader model 不应该机械决定答案长度。

它主要用来发现：

> 用户理解当前论文时真正缺失的 prerequisite 是什么。

---

# 14. Tutor / Prerequisite Mapper

Tutor Agent 不负责总结论文。

它负责检测：

```text
论文当前节点要求什么知识？
reader 当前掌握到什么程度？
差距在哪里？
```

例如用户问：

> 为什么这里梯度可以这样拆？

不要只解释这一行。

Tutor 可能创建：

```yaml
id: P12

topic: computational graph partial derivatives

current_level: 1
required_level: 3

reason:
Needed to understand derivation of Eq. 9.
```

随后可以插入一个局部 prerequisite lesson。

这样长期下来：

```text
reader.yaml
+
prerequisites.yaml
```

逐渐形成用户自己的知识地图。

---

# 15. 用户参与讨论后的状态更新

论文 council 完成只是第一次初始化。

后续用户可能问：

```text
为什么 Eq. 7 要这么设计？

这里如果换成 all-gather 呢？

这个实验是不是没有 isolate communication？

我觉得作者这个结论并不成立。
```

每次讨论后都应该判断：

```text
是否创建新 claim？

是否修改已有 claim？

是否创建 issue？

是否解决 issue？

是否发现 prerequisite？

是否改变 scheme？
```

例如：

```text
conversation
    ↓
new evidence / reasoning
    ↓
update C17
    ↓
resolve I8
    ↓
update scheme.md
```

而不是只在 chat 中回答。

---

# 16. 长上下文控制

后续再次打开论文时，不应该加载全部历史 debate。

默认加载：

```text
source.yaml
scheme.md
claims.yaml
open_questions.md
reader.yaml
```

只有当某个 issue 需要重新审查时才加载：

```text
debates/round-X.md
```

也就是：

> State compression should happen explicitly through structured files, rather than implicitly through conversation summarization.

这是防止 context drift 的核心机制。

---

# 17. 实践 / Reproduction

由于目标不是纯阅读，还需要有一个 optional workflow：

```text
Reproduction Planner
```

不是每篇论文默认启动。

当论文适合实践时，生成：

```text
最低成本验证实验

核心算法 toy implementation

值得读的源码入口

关键 metric

expected behavior

哪些实验对理解设计最有帮助
```

例如系统论文可以输出：

```text
Experiment R1

Question:
Does communication dominate beyond TP=4?

Minimal setup:
...

Measurement:
...

Expected observation:
...
```

目标不是完整复现论文。

而是：

> 找到最有教育价值的最小实验。

---

# 18. Paper Discovery

Paper Discovery 最好作为独立 Skill：

```text
paper-discovery
```

用户可以：

```text
Explore recent work on LLM inference scheduling
```

系统执行：

```text
define topic
 ↓
search recent + foundational work
 ↓
cluster papers
 ↓
identify lineage
 ↓
rank reading value
```

结果不要只是：

```text
10 篇论文列表
```

而应该形成：

```text
Foundational
    ↓
Core lineage
    ↓
Recent branches
    ↓
Open problems
```

例如：

```text
Topic: MoE routing

Foundations
├── Conditional computation
└── Sparsely-Gated MoE

Scaling
├── GShard
├── Switch Transformer
└── ...

Modern routing
├── ...
└── ...

Systems
├── expert parallelism
├── load balancing
└── communication optimization
```

每篇 candidate 给出：

```text
为什么值得读
与哪些论文相关
属于算法 / 系统 / 理论 / 实验哪条线
预计阅读成本
优先级
```

选中后：

```text
discover
   ↓
candidate
   ↓
resolve/download
   ↓
paper-council
```

这样 discovery 和 reading 是同一套 library 的两个入口。

---

# 19. library/index.yaml

repo 应该维护统一论文索引。

例如：

```yaml
papers:

  - id: arxiv:1909.08053
    slug: megatron-lm-2019
    title: Megatron-LM
    status: studied

    topics:
      - tensor-parallelism
      - distributed-training

    priority: high

  - id: arxiv:1701.06538
    slug: sparsely-gated-moe
    status: reading
```

状态可以包括：

```text
candidate
queued
reading
studied
paused
reference
```

这只是 Paper Council 内部的 research state。

不替代 Zotero bibliography。

---

# 20. Reading Queue

Paper discovery 找到的论文可以写：

```text
library/reading_queue.yaml
```

例如：

```yaml
- paper_id: ...
  priority: high

  reason:
    Needed before reading Kimi K3.

  prerequisites:
    - expert parallelism
    - MoE routing
```

以后可以形成：

```text
Read X before Y
```

这样的 dependency graph。

---

# 21. Skill 的职责边界

`SKILL.md` 本身保持短小。

它主要定义：

```text
什么时候触发

读哪些 state

启动哪些 agent

agent 是否隔离

claim/evidence 标准

如何创建 issue

moderator 如何收敛

什么时候更新文件

什么时候加载旧 debate
```

复杂规范拆到：

```text
references/roles.md

references/debate-protocol.md

references/state-schema.md

references/teaching-protocol.md
```

不要把所有东西塞成一个巨大 prompt。

---

# 22. scripts 的职责

凡是 deterministic 的事情尽量不要浪费 LLM reasoning。

例如：

```text
title normalization

DOI / arXiv metadata parsing

paper identity generation

slug generation

PDF cache

workspace initialization

schema validation
```

都应该放：

```text
scripts/
```

Agent 主要处理：

```text
semantic search

paper selection

analysis

criticism

evidence interpretation

teaching

synthesis
```

---

# 23. 用户主要交互方式

不需要一开始设计 CLI 产品。

直接通过 Codex 自然语言即可。

典型 workflow：

### 新论文

```text
Read the Megatron paper.
```

系统自动：

```text
resolve
→ download
→ workspace
→ council
→ debate
→ scheme
```

---

### 已有论文继续讨论

```text
Continue Megatron.

I don't understand why the first GEMM uses column
parallelism rather than row parallelism.
```

系统：

```text
load canonical state
→ answer
→ potentially update claim/scheme/prerequisite
```

---

### 探索领域

```text
Explore the important recent work on
multi-instance LLM inference co-location.
```

系统：

```text
paper-discovery
→ research map
→ candidate queue
```

---

### 实践

```text
For this paper, give me the smallest experiment
that would make the core mechanism concrete.
```

启动：

```text
Reproduction Planner
```

---

# 24. MVP

第一版只需要把最核心闭环跑通。

## 必须实现

```text
paper resolver

PDF downloader/cache

paper workspace

reader profile

4-agent blind review

claim/evidence representation

issue-based cross review

moderator

scheme.md generation

persistent state update

resume existing paper
```

再加一个简单的：

```text
paper-discovery
```

即可。

---

# 25. 暂时不要做

第一阶段不要做：

```text
Web UI

vector database

complex database server

Zotero filesystem parser

full citation manager

PDF annotation editor

automatic knowledge graph visualization

multi-user support

cloud synchronization

full paper reproduction framework
```

这些都会把项目从：

> 改善论文阅读

变成：

> 开发一个论文管理产品。

---

# 26. Zotero 后续集成

如果未来确实觉得有价值，再增加：

```text
Zotero Adapter
```

允许：

```text
通过 title / DOI 找 Zotero item

读取 collection / tags / notes

把 Paper Council 状态关联到 Zotero key
```

甚至可以支持：

```yaml
zotero:
  item_key: ABC123
```

但 PDF analysis 仍然可以使用 Paper Council cache。

这样不会让 Zotero 内部 storage layout 成为 architecture dependency。

---

# 27. 最终可能演化出的 Paper Reader

如果这套 workflow 使用几十篇论文之后证明有效，才考虑把它产品化。

未来 Paper Reader 可以只是当前系统的一层 UI：

```text
                 Paper Council Core

                       │

      ┌────────────────┼────────────────┐
      ↓                ↓                ↓

   Codex UI       Dedicated UI      Zotero Adapter
```

真正需要保留的资产不是 UI，而是：

```text
protocol

role definitions

state schema

claim/evidence model

debate mechanism

reader model

积累下来的 paper states
```

因此当前 repo 的设计应该让这些东西完全独立于未来 UI。

---

# 28. 核心设计哲学

这个项目最终不是：

> AI reads papers for me.

而是：

> AI constructs a contested, evidence-backed map of the paper so that I know what deserves my attention when I read it.

典型流程应该是：

```text
                     Paper
                       │
                       ↓
              Independent Agents
                       │
              ┌────────┴────────┐
              ↓                 ↓
           Claims            Objections
              └────────┬────────┘
                       ↓
                    Issues
                       ↓
                  Moderator
                       ↓
                 Paper Scheme
                       ↓
              ┌────────┴────────┐
              ↓                 ↓
          User Reading       Discussion
              │                 │
              └────────┬────────┘
                       ↓
               Persistent State
                       │
                       ↓
                Deeper Reading
```

最终衡量系统好坏的标准不是 summary 有多完整。

而应该是：

1. 有没有暴露容易被忽略的重要细节；
2. 有没有发现作者 narrative 之外的 alternative；
3. 有没有把 claim 和 evidence 对齐；
4. 有没有明确保存尚未解决的争议；
5. 有没有发现用户真正缺失的 prerequisite；
6. 用户读原文时是否更容易知道哪里应该精读；
7. 讨论几天甚至几个月后，是否还能恢复当初形成的 mental model；
8. 是否能够自然地把理论理解连接到源码、实现和小规模实验。

如果这八件事能做好，这个 repo 就已经达到了目标。
