---
name: paper-council
description: 在 paper-lab 中以四角色独立阅读、证据审计和结构化争议深入理解论文，保存并恢复论文状态。用于读新论文、继续阅读、讨论公式或设计，以及按需规划最小验证实验。
---

# Paper Council

中文解释，保留 technical terms、原始标题、公式及必要原文。默认完整 council。
从仓库根运行脚本，使用 `.venv/bin/python`（环境安装见 README）。

## 新论文
1. 读 profile/reader.yaml、library/index.yaml 和 [状态规范](references/state-schema.md)。
   运行 `scripts/resolve_paper.py QUERY --output .cache/metadata.yaml`。
   标题只返回候选，核对官方页面的作者/年份/标题；有实质歧义才问用户。
   可用 web search 补救 provider 失败，保存核验来源，不伪称脚本已成功。
2. 固定阅读版本，运行 `scripts/download_paper.py .cache/metadata.yaml` 和
   `scripts/create_workspace.py .cache/metadata.yaml --slug SLUG --status reading`。
   无公开 PDF 时可用用户副本；不要凭摘要做完整 council。普通 URL 仅支持
   citation metadata，缺失时从官方来源人工补齐，不编造。
3. 读 [角色定义](references/roles.md)、[讨论协议](references/debate-protocol.md)。
   **实际启动四个新上下文子代理**：mechanism / systems / evidence / adversarial。
   用 `fork_turns="none"` 或等效参数，只传原文路径与 hash、role、reader、唯一输出路径。
   不传主任务分析，不继承聊天。并发不足分批；四个盲读全部完成才交叉审查。
   无子代理能力时记录 blocker，不把单代理模拟四角标为已完成。
4. 每个 reviewer 读完整论文与相关附录，必要时渲染并查看公式、图表原页。
   文本缓存标有 PDF 页码；文本提取不等于视觉核验。
5. 主代理归并候选 claims/issues，按协议进行 issue-based cross-review，随后
   作为 moderator 综合并保留 DISPUTED/OPEN。不得先综合再安排形式化审查。
6. 更新 claims、issues、prerequisites、scheme、open_questions、reading_log、run 和
   library，运行 `scripts/validate_state.py`。交付阅读地图/分歧/精读位置。
   初次 council 完成仍是 reading，不代表用户已掌握或自动变为 studied。

## 继续 / 恢复
运行 `scripts/resume_paper.py SLUG`，加载 source、scheme、claims、issues、
open_questions、prerequisites、run 和 reader，默认不读历史 debates。
中断后按 run 检查已完成阶段，仅补缺失工作；遗漏的盲读仍使用新上下文。
需要出处或重审 issue 才加载相关 memo。讨论改变判断时更新文件，记录理由；
不为每句聊天创造 claim。纠正保留原 ID 并追加 history，scheme 与 YAML 一致。

## Teaching / 实践
需要先修解释时读 [教学协议](references/teaching-protocol.md)。
用户请求实践时规划最小实验，写 question/setup/metric/expected behavior/falsifier；
不默认启动训练、安装论文仓库或占用 GPU。
