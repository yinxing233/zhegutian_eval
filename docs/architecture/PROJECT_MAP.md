# 项目骨架

## 目标

将“宋词生成质量”转化为可复现、可归因、可比较的结构化评测。
诗词只是载体；系统本体是 LLM Eval Pipeline Demo。
评测的本质是**观测系统在约束空间中的行为**，而非对模型进行相对排序或排行榜输出。
本项目的长期方向是成为一个**生成系统动力学观测框架**。

## 系统流

Eval Task（结构化任务定义）
├── 单任务评测：标准评测模式
└── 压力梯度扫描：沿指定维度（韵部限制、禁用词、现代主题距离等）递增约束密度，生成一组梯度任务，用于观测系统在不同压力下的行为变化

→ Generation（batch_generate.py，多 Provider 生成）
→ Local Metrics（规则层：结构 / 平仄 / 押韵 / 对仗）
→ Conditional Semantic Eval（仅在前置规则通过后触发）
→ Failure Pattern Inference（M 症状 → F 诊断标签）
→ Experiment Snapshot（完整实验快照）
→ Badcase Pool / Judge Failure Pool（自动追加）

扰动实验模式（可选路径）：
对已生成的样本施加局部扰动（替换关键意象、调换句子、微调韵脚），
重新送入 Local Metrics → Semantic Eval，观测场域是否崩解。
此模式复用现有评测基础设施，仅在输入端新增扰动步骤。

## 模块边界

- `evaluator.py`：唯一评测入口，负责约束解释、维度组织、总分计算
- `metrics/*`：纯评分函数，不读取任务语义层
- `llm_client.py`：LLM 调用封装，仅供 LLM-based metrics 和裁判检查使用
- `batch_generate.py`：批量生成与快照透传
- `batch_evaluate.py`：批量评测、条件语义评测、badcase 归档
- `analysis/`：塌缩模式分析、压力—响应统计（未来扩展）

## 核心不变量

1. L0 可进入执行逻辑；L1/L2 只用于分析，不参与评分。
2. `evaluator` 是唯一评测入口，pipeline 不得绕过它直连 metric。
3. `semantic_score = None` 不是低分，而是缺失；缺失原因必须显式记录。
4. badcase 必须保留完整实验快照。快照不仅用于复现，也是塌缩路径分析和跨模型压力对比的数据基础。
5. judge failure 不得污染模型评分。
6. 本评测系统不对模型进行相对排序或排行榜输出。评测目标是观测系统在约束空间中的行为，而非判断“谁更好”。
