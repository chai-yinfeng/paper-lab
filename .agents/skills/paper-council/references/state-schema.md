# Canonical state v1

YAML 顶层 mapping，`schema_version: 1`。时间是 ISO 8601 字符串，路径相对仓库根。

- source.yaml：title/authors/year、paper_id、aliases、slug、doi/arxiv_id、version、
  canonical_url/pdf_url、metadata_source、retrieved_at。document 包含 sha256、version、
  page_count、pdf_path/text_path/pages_path、download_url、retrieved_at、access_basis。
  year 为首次发表年份，arxiv_id 无 vN，version 是实际阅读版。
- claims.yaml 的 claims：id=C数字、statement、type=SOURCE/DERIVED/SPECULATION、
  status=CONFIRMED/DISPUTED/OPEN/REJECTED、confidence=high/medium/low、confidence_reason、
  evidence、history。每条 evidence 有 source_sha256、page（1 起始 PDF 页码）、
  至少一个 section/equation/figure/table/algorithm/appendix/locator，以及 note（支持范围）。
  SOURCE/DERIVED 必须有证据；DERIVED 另有非空 depends_on 和 reasoning；
  SPECULATION 有 testable_by，不能 CONFIRMED。不能猜 locator 或精确数字。
  当前 evidence 仅校验本篇 PDF；外部资料在 source.external_sources 登记 id/URL/
  version/检索日期，写 provenance 并明确不是本篇证据。
- issues.yaml 的 issues：id=I数字、title、related_claims、positions（role/position/
  evidence）、status、resolution、remaining_uncertainty、history。positions 的证据
  使用与 claim 相同的 locator 格式。
- prerequisites.yaml 的 prerequisites：id=P数字、topic、current_level=unknown/0..4、
  required_level=0..4、reason、related_claims、status=unassessed/learning/resolved、basis。
- scheme.md：引用 C/I/P 的可读 mental model。包含 Problem、Core Thesis、Mental Model、
  Architecture / Algorithm、Key Design Decisions、Assumptions、Claim → Evidence Map、
  Engineering Implications、Alternatives、Disputed Issues、Prerequisite Gaps、
  Reproduction Opportunities、What I Should Read Carefully、What Can Be Skimmed、Open Questions。
- open_questions.md：未决 issues 的阅读入口，不另存冲突判断。
- reading_log.md：时间、变更 IDs、原因、后续动作，不保存逐字聊天。
- run.yaml：phase、source_sha256、blind_reviews/cross_reviews mapping、rounds_completed、
  updated_at；每个 review 有 memo（仓库相对路径）、agent_id、source_sha256、completed_at。
  完整运行需要四份 blind、至少两份 cross-review、非空 claims 和所有状态文件。

Library index 的 papers：id、aliases、slug、title、status、topics、priority。
status=candidate/queued/reading/studied/paused/reference；discovery candidate 可以无 workspace。
Queue 的 queue：paper_id、priority、reason、prerequisites（paper IDs，无依赖用 []）。
概念型先修知识放 prerequisites.yaml，不混入论文依赖图。

Reader knowledge 每项 level=unknown/0..4，basis 是具体自述/讨论观察依据。
0 不熟悉，1 识别，2 解释后理解，3 独立推导/实现，4 批判/修改/设计。
unknown 不是 0，不复制示例画像，不凭一个问题判断用户能力。

ID 在单篇内稳定、递增、不复用。修正追加 history: at/change/reason，保留原 ID。
合并保留旧项并写 superseded_by；错误判断用 REJECTED，不删除审计轨迹。
CONFIRMED 含义由 statement 的范围决定，不等于独立复现或普遍真理。
