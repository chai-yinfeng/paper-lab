# MVP decisions

2026-09-10。原始输入保存在 [design brief](original-design-brief.md)。

用户确定：中文解释并保留术语/必要原文；默认完整 council，混合预读后置；
Megatron-LM 为首篇；使用 Git，后续同步 GitHub。

实施决定：

1. repo 名为 paper-lab；仓库技能位于 `.agents/skills/`。
2. 四个实际 fresh-context reviewer 分批执行，遵守共享文件系统的盲读协议，
   不声明硬隔离。主代理不向仍盲读的角色传结论。
3. 增加 issues.yaml 和 run.yaml；结构化判断是分析状态的权威来源，scheme 是阅读视图。
   原文仍是论文事实的权威，不能把持久化状态误当不可质疑的真理。
4. paper identity 与 source version 分开，arXiv/DOI aliases 去重；PDF 按版本/hash 缓存。
   PDF 页码从1开始，来源 hash 绑定每条证据；MVP 拒绝静默换版。
5. SOURCE/DERIVED/SPECULATION 明确区分；confidence 为 high/medium/low + 理由。
6. 主代理统一写正式状态与 ID，reviewer 仅写指定 memo；文件原子替换，脚本写入带仓库锁。
   多文件修改以校验+Git快照收敛，不宣称数据库级多文件事务。
7. Reader 初始 unknown，不沿用方案示例分数。Council 完成默认 reading，不自动 studied。
8. 默认一轮 issue-based cross-review，至少两位 reviewer；有新证据才追加一轮。
9. Discovery 为独立自然语言技能+web tools，搜索结果可入候选索引，不自动深读全部候选。
10. 无 Web UI、API模型调用服务、Zotero解析、OCR、自动训练或额外数据库。

接口依据：
- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)

本地 Git 使用 main。远程地址与 visibility 尚未指定，不创建 GitHub 仓库。

## 2026-09-11：设计方向更新

以上为旧版历史设计，后续以本节为准。内置对话作为主要入口，支持通用 LLM API；
默认 Specialist，Reader + Checker 按需运行，完整 council 保留为显式选项。
用户论文、scheme、对话、笔记和阅读状态不进入 GitHub。数据目录可由用户指定，
实现与测试前由用户指定临时测试数据目录，当前不执行真实论文验证。
Megatron-LM 旧版阅读产出及其验收记录已移除，并重建 Git 发布历史。
UI、provider 接口及可配置数据目录尚未实现。
