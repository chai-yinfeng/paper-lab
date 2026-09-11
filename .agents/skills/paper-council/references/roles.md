# 独立角色与 memo contract

每个角色从固定版原文出发，完整阅读，不只读摘要。中文重建，保留术语；
重要判断附 PDF page + section/figure/table/equation。转述而非大量摘录原文。

- mechanism：重建 problem、张量形状、数学目标、forward/backward、算法与假设；
  用最小数据流说明可拆分/交换的操作及非线性、依赖造成的限制。
- systems：重建组件、数据分片/复制、collective、memory/compute/communication；
  找出缺失实现细节、硬件和运行时限制。未核验现代代码不能证明历史实现。
- evidence：独立建立 claim → experiment/derivation；检查分母、baseline、控制
  变量、ablation、数据处理与统计支持。作者报告不等于我们已独立复现。
- adversarial：针对 major decisions 提出可行 alternative、hidden assumption、
  independent hypothesis 和可区分解释的证据。没比较不等于方法无效。

Memo 记录 role、version/hash、读过的页、视觉检查页、blind 隔离声明。
用 M1/S1/E1/A1 等角色局部 ID，正式 C/I ID 后由 moderator 分配。
包含核心重建、带证据候选判断、质疑/替代解释、未决问题、精读建议。
只能读取原文、reader、自己的角色协议与 memo；不能读其他 memo/已有 scheme/
其他 agent 消息/主代理总结，不能写 canonical state。共享文件系统下是协议
隔离，不能宣称访问权限上的硬隔离。
