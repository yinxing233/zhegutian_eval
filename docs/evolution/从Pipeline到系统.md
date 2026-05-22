# 从 Pipeline 到实验系统

最初系统采用：

生成 → 立即评测

的一体化 pipeline。

这在 MVP 阶段足够简单。

但很快暴露出问题：

- 修 evaluator 需要重新生成
- 修 badcase 要重新消耗 API
- 不同 evaluator 无法对同一批结果复验
- 生成失败与评测失败互相污染

系统逐渐意识到：

生成与评测，
实际上属于两种完全不同的生命周期。

生成是：

- 高成本
- 不稳定
- 外部依赖
- 一次性采样

而评测是：

- 可重复
- 可回放
- 可演化
- 可对照实验

于是系统开始拆分：

batch_generate.py
→ generated_results.jsonl
→ batch_evaluate.py

中间产物被冻结。

生成结果开始被视为实验产物。

而 evaluator 则变成可复现的观测系统。

这次演化之后，系统不再只是一个 pipeline。

而开始具有实验系统的性质。

即：

同一批生成结果，
可以被：

- 不同 evaluator
- 不同 本体（ontology）
- 不同 不稳定性指标

反复重新解释。
