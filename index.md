# 鹧鸪天：大模型失败模式观测器

> 一个用于观察大模型在高约束生成任务中，如何失稳、崩塌与退化的结构化评测系统。

---

## 研究假设

> 高约束生成中的失败可能具有可重复结构；本项目通过冻结 generation、
> 版本化 evaluator 和 badcase corpus 检验这一假设。

我们追问的不是“模型成功了吗？”，而是“**模型是怎样失败的？**”
当 Benchmark 分数趋同，真正的能力边界开始隐藏在失败结构里。

---

## 观测维度

- **约束场 (Constraint Field)**：以《鹧鸪天》词牌构造密集的格律‑语义耦合压力。
- **结构化失败 (Structured Failure)**：失败不是噪声，而是携带模型内部结构信息的关键数据。
- **失败原型 (Failure Prototype)**：记录 `template_parroting`、`reasoning_overflow` 等候选失稳模式及其证据边界。
- **增量快照 (Delta Snapshot / ΔS)**：观测不同实验间失败模式的动力学漂移。

---

## 快速导航

- [📖 项目总览与快速开始](https://github.com/yinxing233/zhegutian_eval)
- [💡 设计哲学](./docs/philosophy/philosophy.md) – 为何这样定义评测
- [🏗️ 系统工程与架构](./docs/architecture/architecture.md)
- [📐 当前评测契约](./docs/architecture/EVALUATION_CONTRACT.md)
- [🗂️ 项目骨架](./docs/architecture/PROJECT_MAP.md)
- [📚 概念定义](./docs/philosophy/concepts.md)
- [⌚️ 未来方向](./docs/philosophy/future.md)

---

## 一则典型观测

> “模型并非随机失败。当约束过载时，它会沿着自身结构最薄弱的方向发生退化——有时为了语义完整放弃押韵，有时因‘思考过载’而未能动笔。”
