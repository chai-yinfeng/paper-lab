---
name: paper-discovery
description: 在 paper-lab 中探索研究主题的经典与近期论文，形成有来源的研究脉络、候选列表和阅读依赖队列。用于领域探索和选论文，不替代单篇完整 council。
---

# Paper Discovery

中文解释，保留原始标题和术语。读 profile/reader.yaml、library/index.yaml、
library/reading_queue.yaml、discovery/topics.yaml；遵循
`../paper-council/references/state-schema.md`。

1. 确定主题边界和时间范围；“近期”默认最近 24 个月，写执行日期，同时检索经典工作。
2. 用可用 web search 搜索并实际打开 arXiv、conference proceedings、出版社/作者页面。
   记录 query、URL、日期、覆盖局限；无联网时不声称完成近期检索。
   只有摘要就标 abstract-only，不冒充已阅读全文。
3. 建立 foundational → core lineage → recent branches → open problems 地图。
   关系注明作者引用还是 agent 推断。每个候选写 title/authors/year/ID/URL、方向、
   阅读价值、相关工作、预计成本（估计）、优先级和依据。
4. 报告写 discovery/reports/YYYY-MM-DD-topic.md，更新 topics.yaml 的
   id/query/searched_at/report。核验候选身份、去重后加入 index（candidate，可无 workspace）。
   用户请求队列或明确优先次序时写 queue: paper_id/priority/reason/prerequisites；
   依赖是已索引 paper ID，检查环路。选中前不需要每篇下载 PDF。
5. 用户选中后交给 paper-council 完整流程，不因找到候选自动启动全部 council。

用 scripts/resolve_paper.py 辅助解析，title similarity 不当语义相关度。
主代理统一更新索引/队列，保留现有 reading/studied 状态，运行 scripts/validate_state.py。
