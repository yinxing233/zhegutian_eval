# 代码审查报告

> 审查范围：`docs/` 全部 20 篇文档 + `src/`、`utils/`、`tools/`、`batch_*.py` 全部源码 + 配置文件

---

## 一、代码 Bug（确认存在，需修复）

### Bug-1: 对仗规则配置从未被实际使用（`evaluator.py`）

**严重性：高**

`evaluator.py` 第 88-119 行尝试从 `special_rules.antithesis` 中提取 `required_pairs` 和 `recommended_pairs`。但 `_object_to_dict(sr.antithesis)` 返回的字典结构为：

```python
{
    "required": [{"pair": [3, 4], "desc": "...", "type": "strict", "weight": 1.0}],
    "recommended": [{"pair": [5, 6], "desc": "...", "type": "soft", "weight": 0.5}]
}
```

之后遍历时：

```python
for pair in required_pairs:
    if isinstance(pair, list) and len(pair) == 2:  # ← pair 是 dict，不是 list！
```

`pair` 是 `{"pair": [3,4], ...}` 字典，`isinstance(pair, list)` 永远为 `False`。代码始终落入 fallback 硬编码 `[[3,4]]` / `[[5,6]]`。虽然碰巧值相同，但规则 JSON 中的 `desc`、`type`、`weight` 全部被丢弃。

### Bug-2: `check_antithesis` 收到的是整个对仗配置而非单条规则（`evaluator.py` → `antithesis.py`）

**严重性：中**

第 104-106 行传入 `antithesis_config`（整个 `{"required":[...], "recommended":[...]}` 字典），但 `antithesis.py` 第 36-42 行尝试从中取 `desc` 和 `type`：

```python
desc = rule_antithesis.get("desc")      # None — 顶层没有这个 key
rule_type = rule_antithesis.get("type")  # None
```

LLM 裁判永远拿不到具体的对仗规则描述，`extra_instructions` 始终为空。

### Bug-3: `skip_semantic=True` 时语义结果缺少 `success` 字段（`evaluator.py`）

**严重性：中**

第 122-126 行：

```python
if skip_semantic:
    semantic_result = {
        "score": 0.0,
        "reason": "语义评测已跳过（skip_semantic=True）",
    }
    # ← 没有 "success" 字段
```

后续第 169 行 `semantic_result.get("success", True)` 默认返回 `True`，导致 `semantic_evaluated` 判断依赖 `skip_semantic` 而非 `success` 字段。虽然当前逻辑恰好正确（因为先检查 `skip_semantic`），但一旦有人重构条件顺序就会出 bug。

### Bug-4: 无对仗结果时默认给满分 20.0（`evaluator.py`）

**严重性：中**

第 367-373 行：

```python
if antithesis_results:
    avg_anti = sum(r["score"] for r in antithesis_results) / len(antithesis_results)
    scores["antithesis"] = round(avg_anti * 20, 2)
else:
    scores["antithesis"] = 20.0  # ← 没检查就给满分
```

如果生成结果不足 4 句（结构严重不完整），对仗模块不执行，直接得 20 分。这意味着一首只有 2 句的残词，对仗维度反而拿了满分。

### Bug-5: `batch_evaluate.py` replay 时 badcase 和 judge_failures 重复累积

**严重性：中**

`eval_results.jsonl` 以 `"w"` 模式写入（覆盖），但 `badcase_pool.jsonl` 和 `judge_failures.jsonl` 以 `"a"` 模式写入（追加）。对同一 run 目录重跑评测时，badcase 和 judge failure 记录会翻倍。`debt002.md` 中已描述了这个问题和清理方案，但未实现。

### Bug-6: `infer_instability_pattern` 中 `truncated` 和 `generation_truncated` 的 finish_reason 不一致

**严重性：低**

`evaluator.py` 第 269 行检查 `finish_reason == "length"`，但 `batch_evaluate.py` 第 235 行检查 `finish_reason == "MAX_TOKENS"`。不同 provider 返回的 finish_reason 格式不同：
- Gemini: `FinishReason.MAX_TOKENS` → `str()` 后为 `"MAX_TOKENS"`
- DeepSeek/GLM: `"length"`

导致 Gemini 的截断被 `infer_instability_pattern` 捕获为 `truncated`，而 DeepSeek/GLM 的截断只被 `batch_evaluate.py` 的后处理捕获为 `generation_truncated`，两者诊断路径不一致。

### Bug-7: `is_badcase` 逻辑导致几乎所有样本都被标记为 badcase

**严重性：中**

`batch_evaluate.py` 第 242-248 行：

```python
is_badcase = (
    normalized_score < 60
    or len(error_category) > 0
    or ...
)
```

`infer_instability_pattern` 的兜底逻辑（第 321-322 行）保证 `tags` 永远非空——即使一切正常也会加入 `unknown_instability`。而 `safe_mediocrity` 在语义分 10-14 时触发。这意味着除非语义分 > 14 且无任何 M 层异常，否则样本都会被标记为 badcase，导致 badcase pool 失去筛选价值。

---

## 二、文档与代码不一致

### Doc-1: 架构文档引用了不存在的 `src/utils.py`

`docs/describe.md` 和 `docs/阶段性总结.md` 都将 `src/utils.py` 描述为工具层。实际代码中工具层已重构为 `utils/` 包（`text_utils.py`、`text_cleaner.py`、`extractor.py`），位于项目根目录而非 `src/` 内。

### Doc-2: 架构文档引用了不存在的 `run_eval.py`

`docs/describe.md` 和 `docs/阶段性总结.md` 都描述了 `run_eval.py` 作为入口脚本。实际入口已拆分为 `batch_generate.py` 和 `batch_evaluate.py`。`run_eval.py` 不存在。

### Doc-3: 架构文档引用了不存在的 `test_generator.py`

`docs/阶段性总结.md` 提到 `test_generator.py` 作为临时测试脚本，但项目中无此文件。

### Doc-4: `describe.md` 遗漏 `semantic.py`

`describe.md` 的 metrics 部分只列了 `pingze.py`、`rhyme.py`、`antithesis.py`，遗漏了实际存在的 `semantic.py`。

### Doc-5: README 引用了错误路径

- README 第 357 行引用 `docs/engineering/PROJECT_MAP.md`，实际路径是 `docs/architecture/PROJECT_MAP.md`
- README 第 209 行引用 `docs/bad_cases.md`，此文件不存在

### Doc-6: `philosophy.md` 引用了不存在的 `docs/engineering/`

第 55 行："具体怎么走，是 `docs/engineering/` 和 `docs/evolution/` 中的文档要解决的事"。`docs/engineering/` 不存在，实际为 `docs/architecture/`。

### Doc-7: `concepts.md` 引用了不存在的 `evolution/COGNITIVE_SHIFTS.md`

第 141 行提到"应当记录在 `evolution/COGNITIVE_SHIFTS.md` 中"，此文件不存在。

### Doc-8: `阶段性总结.md` 中模型名称与代码不一致

文档中 `.env` 示例写 `GEMINI_MODEL=gemini-3.0-flash`，代码默认值为 `gemini-3-flash-preview`。两者都不是有效的 Gemini 模型名（应为 `gemini-2.0-flash` 或类似）。

### Doc-9: `阶段性总结.md` 描述生成层"当前支持 Gemini"，但代码已支持三家

文档说"当前实现 Gemini，预留 DeepSeek/OpenAI 接口"。实际代码已实现 Gemini、DeepSeek、GLM 三个 provider。

### Doc-10: `describe.md` 未描述 `batch_generate.py` 和 `batch_evaluate.py`

旧架构文档只描述了单体 `run_eval.py` 流程，未反映已拆分的生成/评测解耦架构。`architecture.md` 有更新但仍标注 `src/main.py` 为程序入口，而 `main.py` 实际只做规则结构打印。

### Doc-11: `debt002.md` 描述的评测版本隔离方案未实现

文档详细描述了 `evaluations/eval_v0.2.2/` 目录结构和 replay 清理逻辑，但 `batch_evaluate.py` 仍直接写入 run 目录根，`eval_version` 变量定义了却未用于目录隔离。

---

## 三、架构设计问题

### Arch-1: `skip_semantic` 不跳过 antithesis（LLM 调用）

`evaluator.py` 的 `evaluate(skip_semantic=True)` 仍然执行对仗检查（`check_antithesis`），而后者是 LLM-based 的。这与 `DESIGN_DECISIONS_ARCHIVE.md` Decision 004 的设计原则矛盾——"格律崩坏的词也浪费 API 配额去评语义"。对仗同样消耗 API 配额，应同样支持跳过。

### Arch-2: `LLMClient.__new__` 返回子类实例而非自身

`llm_client.py` 使用 `__new__` 实现工厂模式，返回 `GeminiEvalClient` 等子类实例。这导致 `isinstance(LLMClient(), LLMClient)` 为 `False`，违反类型直觉。应改为独立的工厂函数。

### Arch-3: 导入路径不一致

- `evaluator.py` 使用 `from src.metrics.antithesis import ...`（`src.` 前缀）
- `main.py` 使用 `from schema.rule_config import ...`（无 `src.` 前缀）
- `evaluator.py` 使用 `from utils.text_utils import ...`（`utils` 在项目根，不在 `src` 内）
- `pyproject.toml` 设置 `package-dir = {"" = "src"}`，但 `utils/` 在 `src/` 之外

这种混合导入方式依赖 `sys.path.insert` 手动注入才能工作，不够健壮。

### Arch-4: `check_antithesis` 和 `check_semantic` 每次调用都创建新的 `LLMClient`

```python
def check_antithesis(...):
    client = LLMClient()  # 每次都新建
```

一次评测中如果有 required + recommended 对仗，会创建 2+ 个 LLM 客户端实例，每个都会初始化 API 连接。应复用客户端。

### Arch-5: 评测覆盖率逻辑分散在两处

`_compute_overall` 只返回 `total`/`breakdown`/`max_total`，不包含 coverage。覆盖率和缺失维度的计算逻辑散落在 `batch_evaluate.py` 中。如果直接调用 `evaluator.evaluate()`，得不到 coverage 信息，违反了"evaluator 是唯一评测入口"的原则。

### Arch-6: `infer_instability_pattern` 忽略对仗分数

该方法接收 `metrics` 字典（含 `antithesis` 分数），但诊断逻辑中从不使用 `antithesis`。低对仗分可能指向 `F_identity` 或 `F_symbolic`，但完全未被利用。

### Arch-7: `pyproject.toml` 入口点配置错误

```toml
[project.scripts]
zhegutian = "main:main"
```

`main.py` 在 `src/` 目录下，但 `package-dir = {"" = "src"}` 意味着包内导入应该是 `main:main`。然而 `main.py` 自身的导入 `from schema.rule_config import ...` 在打包安装后可能无法正确解析。且 `main.py` 只做规则打印，不是真正的 pipeline 入口。

---

## 四、技术债与未实现计划

### Debt-1: 评测版本隔离（`debt002.md`）

完整的目录结构改造、replay 清理、`eval_metadata.json` 写入、`--replay` CLI 参数均未实现。

### Debt-2: `[END]` stop token 仍配置但 prompt 已移除指令（`debt001.md`）

`generator.py` 仍设置 `stop_sequences=["[END]"]`，但 prompt 已不提及 `[END]`。这是已知的技术债，低优先级。

### Debt-3: reasoning leakage 与 empty output 未区分（`debt001.md`）

DeepSeek 推理泄漏时返回空正文，被归为 `empty_output`，可能丢失高信息密度的诊断数据。

### Debt-4: 缺少 `.env.example` 文件

README 引导用户 `cp .env.example .env`，但项目中不存在 `.env.example`。

### Debt-5: 概念层 F 层标签未完整实现

`concepts.md` 定义了 5 个 F 层标签（`F_identity`、`F_temporal`、`F_symbolic`、`F_imagery`、`F_emotional`），但代码中只使用了 `F_imagery` 和 `F_emotional`。`F层的设计演化.md` 说明这是有意识的 MVP 妥协，但文档与代码的差距应更显式标注。

### Debt-6: `aesthetic_entropy` 标签未在文档中记录

`evaluator.py` 中存在 `aesthetic_entropy` 症状标签（`primary_field: "F_emotional"`），但 `concepts.md` 和 `F层的设计演化.md` 均未提及此标签的定义和归类。

---

## 五、数据与配置问题

### Data-1: 韵部映射表可能的正确性问题

`data/zhonghua_xinyun.json` 中：
- `"i"` → `"六鱼"`：在标准中华新韵中，`i`（如 bi/pi/mi）通常属于"七齐"，"六鱼"应为 `ü` 音
- `"u"` → `"五支"`：`u`（如 bu/pu/mu）通常不属于"五支"
- `ü` 和 `üe`/`ün` 作为独立 key 存在，但 pypinyin 的 TONE3 格式可能返回 `v` 而非 `ü`，导致匹配失败

建议交叉验证韵部表与标准中华新韵十八韵对照。

### Data-2: `text_utils.py` 的 `split_into_lines` 会删除所有非汉字字符

对于 `modern_04_topic`（程序员加班）这类现代主题，如果模型输出了英文字符（如 "bug"、"code"），这些字符会被 `HAN_ONLY` 正则完全删除，可能导致断句异常或字数不匹配。

### Data-3: 模型默认值可能无效

- `generator.py` 第 371 行：`gemini-3-flash-preview` — 非已知的有效 Gemini 模型名
- `generator.py` 第 380 行：`deepseek-v4-flash` — 非已知的有效 DeepSeek 模型名
- `generator.py` 第 389 行：`glm-4.5-air` — 非已知的有效 GLM 模型名

这些默认值仅在环境变量未设置时生效，但可能导致 API 调用失败。

---

## 六、优先级建议

| 优先级 | 编号 | 问题 |
|--------|------|------|
| **P0** | Bug-1 | 对仗规则配置从未被使用 |
| **P0** | Bug-4 | 无对仗结果时默认给满分 |
| **P0** | Bug-7 | 几乎所有样本都被标记为 badcase |
| **P1** | Bug-2 | check_antithesis 收到错误的配置层级 |
| **P1** | Bug-3 | skip_semantic 时缺少 success 字段 |
| **P1** | Bug-5 | replay 时 badcase 重复累积 |
| **P1** | Arch-1 | skip_semantic 不跳过 antithesis |
| **P1** | Arch-3 | 导入路径不一致 |
| **P2** | Bug-6 | finish_reason 不一致 |
| **P2** | Arch-2 | LLMClient __new__ 反模式 |
| **P2** | Arch-4 | LLMClient 重复创建 |
| **P2** | Arch-5 | 覆盖率逻辑分散 |
| **P2** | Arch-6 | 对仗分数未用于诊断 |
| **P2** | Doc-1~11 | 文档与代码不一致 |
| **P3** | Debt-1~6 | 技术债 |
| **P3** | Data-1~3 | 数据与配置问题 |
