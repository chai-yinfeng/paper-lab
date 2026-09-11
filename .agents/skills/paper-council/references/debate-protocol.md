# Execution checkpoints

run.phase: resolved → acquired → blind_review → cross_review → synthesis → complete。
失败保留阶段并记 blocker，恢复后清除。主代理记录 reviewer agent_id、memo 路径、
source_sha256、completed_at、isolation: fresh-context-protocol。
新一轮完整阅读使用新 debates 子目录，保留历史状态与变更理由。

## Blind pass
四个 reviewer 都 fresh context，无 fork 历史，只接收固定源、角色、reader 与输出路径。
主代理可以阅读返回结果，但不能传给尚未完成的盲读 reviewer。四角齐全才公布 memo。

## Cross-review
主代理保留原 memo，归并重复候选，分配 C/I ID，创建 initial-review.md，写
local → canonical ID 映射与待审议题，暂不作 moderator 最终结论。
至少两个 reviewer 交叉审查其他角色的重要判断，默认 mechanism + evidence。
每个 issue 写 related claims、positions、正反证据、区分解释所需观察、建议状态与理由。
所有 substantive objections 都要明确 disposition，不以赞同为奖励。
默认一轮，只有新证据/关键矛盾值得时追加一轮，默认最多两轮，不无限求共识。

## Moderator / sole writer
Cross-review 完成后才 synthesis；逐 issue 决定 CONFIRMED/DISPUTED/OPEN/REJECTED。
保留 positions、理由、remaining uncertainty、memo provenance；票数不是证据。
DERIVED 写 dependencies/reasoning；SPECULATION 写可检验条件。
先写 YAML 再写 scheme/open_questions，校验通过后最后设 run complete。
reading_log 记录时间、C/I/P 变更、原因、版本及后续动作。Git 快照不替代稳定 ID。

## Resume / versions
按源 hash 检查已完成 memo，只补缺失角色/阶段，不复用其他版本结果。
更换 PDF 需显式迁移：保留旧 source 与分析快照，逐 claim 重新验证 locator。
MVP 脚本拒绝静默覆盖；迁移在用户请求换版时由主代理处理。
