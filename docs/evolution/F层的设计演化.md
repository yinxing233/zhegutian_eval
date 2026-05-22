````markdown
# Failure Ontology 演化记录：从扁平标签到分层失稳场

## 背景

在对 `src/evaluator.py` 的系统审计中，我们发现当前 failure tagging 系统已经出现了“命名空间漂移”现象。

当前代码中的标签：

```python
[
    "reasoning_overflow",
    "empty_output",
    "tone_fail",
    "template_parroting",
    "F_imagery",
    "safe_mediocrity"
]
```
````

实际上混杂了三种不同层级的对象：

| 类型                         | 示例                              |
| ---------------------------- | --------------------------------- |
| 可观测症状（symptom）        | `tone_fail`, `template_parroting` |
| 失稳场（field）              | `F_imagery`                       |
| 宏观失稳模式（meta pattern） | `safe_mediocrity`                 |

这意味着：

> 当前 taxonomy 并不是一个稳定 ontology，而是不同抽象层的混合投影。

---

# 一、关键发现：F层不是“标签”，而是潜在失稳空间

最初我们倾向于：

```python
{
    "symptom": "template_parroting",
    "field": "F_symbolic"
}
```

但在进一步审视 concepts.md 后，发现：

> symptom 与 field 并非同维变量。

它们的关系更接近：

```text
latent instability field
        ↓
failure dynamics
        ↓
observable symptom
```

也就是说：

- `F_imagery`
- `F_symbolic`
- `F_emotional`

并不是“症状名称”。

它们更像：

> 潜在失稳流形（latent instability manifold）

而：

- `template_parroting`
- `coherence_collapse`
- `tone_fail`

才是最终可观测的 failure 投影。

这也解释了 concepts.md 中的重要定义：

> 同一个 F 崩塌，可以在多个 M 上表现出症状；
> 同一个 M 异常，也可能来自不同 F 崩塌。

因此：

```text
symptom ↔ field
```

理论上是：

```text
many-to-many
```

而不是：

```text
one-to-one
```

---

# 二、MVP阶段的关键妥协

虽然理论上 symptom 与 field 是多对多关系，但 MVP 阶段不应直接进入：

```python
{
    "symptom": "...",
    "fields": [...]
}
```

原因在于：

> failure corpus 尚不足以支撑稳定的 latent disentanglement（潜变量解缠）。

如果在数据规模尚小的阶段直接允许：

```python
["F_identity","F_temporal", "F_symbolic", "F_imagery","F_emotional"]
```

同时出现，会导致：

- field 区分力迅速下降
- badcase 聚类失效
- taxonomy 泛化塌缩
- 所有 failure 最终都变成“多场崩塌”

系统将失去统计意义。

因此，MVP阶段决定：

> 暂时只记录“主导失稳方向”。

即：

```python
{
    "symptom": "...",
    "primary_field": "..."
}
```

注意：

这里故意使用：

```python
primary_field
```

而非：

```python
field
```

其含义是：

> 承认多因性存在，但当前观测器只保留 dominant failure attractor（主导失稳吸引子）。

这是一个有意识的工程化妥协。

---

# 三、关于 template_parroting 的重新归类

最初曾将：

```text
template_parroting
    → F_symbolic
```

但后续推导发现这是错误映射。

原因在于：

## F_symbolic 的定义

象征系统崩塌强调的是：

> 已建立的象征未被后文回收。

例如：

- 引入“孤雁”
- 但后文情感线完全脱离其象征意义

这是：

```text
symbolic inconsistency
```

而：

## template_parroting 的核心病理

模板化复读的本质不是：

> 象征建立失败

而是：

> 根本没有形成高张力意象空间。

其表现为：

- 高频词安全滑行
- 局部句子合理
- 句间不存在远程意象约束
- 情感推进曲线趋于平坦

因此它更接近：

```text
imagery manifold collapse
```

即：

```text
template_parroting
    → F_imagery
```

---

# 四、“崩解（fragmentation）”的定位问题

文档中的“结构崩解”定义为：

> 语法混乱、意象堆砌、句间语义断裂、情感曲线剧烈震荡。

经过分析后发现：

它并不像：

```text
tone_fail
```

这样的单点 symptom。

它更像：

> 多个 symptom 共同形成的高阶宏观失稳态。

即：

```text
coherence_collapse
+
emotion_drift
+
imagery_random_walk
```

共同触发后形成的：

```text
fragmentation
```

因此严格来说：

```text
fragmentation
```

更适合作为：

```text
meta-pattern
```

而非普通 symptom。

理论上的完整结构应为：

```text
symptom
    ↓
primary_field
    ↓
meta_pattern
```

例如：

```python
{
    "symptom": [
        "coherence_collapse",
        "emotion_drift"
    ],

    "primary_field": "F_imagery",

    "meta_pattern": "fragmentation"
}
```

---

# 五、为什么 MVP 阶段暂不引入 meta-pattern 层

虽然 meta-pattern 在理论上更准确，但当前阶段不适合实现。

原因：

> meta-pattern 依赖大量稳定 failure corpus。

否则：

- “fragmentation”
- “constraint_overload”
- “symbolic leakage”

这些名称会迅速退化成：

> 主观哲学命名。

而不是：

> 可统计、可复现、可比较的结构性模式。

因此当前决定：

> 暂时将 fragmentation 降级为普通 symptom 使用。

这是一个刻意保持系统“工程抓地力”的选择。

---

# 六、当前阶段真正目标

当前项目最重要的，不是：

```text
完成哲学体系
```

而是：

```text
稳定 failure ontology
```

即确保：

```text
输入
    ↓
评测
    ↓
failure tagging
    ↓
badcase 沉淀
    ↓
统计分析
    ↓
prompt/rule 修正
```

这条实验闭环能够长期稳定运行。

---

# 七、当前危险信号

本轮讨论中，我们明确识别出一个关键风险：

```text
taxonomy复杂度增长
    >
failure corpus增长
```

一旦出现：

- field 数量扩张过快
- meta-pattern 过早引入
- symptom 命名哲学化
- 远程耦合提前形式化

系统会迅速进入：

> “概念增殖”状态。

其结果是：

- 标签不可统计
- badcase 不可聚类
- 历史版本不可比较
- ontology 漂移
- 工程观测能力下降

因此：

> 每新增一个概念，都必须对应一个稳定、可复现、可观测的 failure 增益。

这是当前阶段最重要的不变量。

```

```
