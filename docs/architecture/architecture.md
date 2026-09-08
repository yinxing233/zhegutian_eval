# 项目架构 / Project Architecture

当前目录与运行产物结构如下；评测字段语义以
[`EVALUATION_CONTRACT.md`](EVALUATION_CONTRACT.md) 为准。

```text
zhegutian-eval/
├── data/
│   ├── eval_zhegutian.jsonl       # L0/L1/L2 任务定义
│   └── zhonghua_xinyun.json       # xinyun_14 音韵数据
├── rules/
│   └── zhegutian_zhengti.json     # 词牌结构与默认 prosody profile
├── src/
│   ├── metrics/
│   │   ├── pingze.py              # 确定性平仄观测
│   │   ├── rhyme.py               # 确定性押韵观测
│   │   ├── antithesis.py          # LLM 对仗裁判
│   │   └── semantic.py            # LLM 语义裁判
│   ├── schema/rule_config.py      # 规则 schema 与交叉校验
│   ├── prosody.py                 # 音韵 profile 边界
│   ├── evaluator.py               # 唯一评测入口与 taxonomy
│   ├── generator.py               # 多 provider 生成实现
│   ├── llm_client.py              # 评测裁判客户端工厂
│   └── main.py                    # 规则诊断入口
├── utils/
│   ├── text_utils.py              # 断句、拼音、声调、韵母规范化
│   ├── text_cleaner.py            # 通用最小清洗
│   └── extractor.py               # GLM 粗粒度正文 salvage
├── tools/
│   ├── delta_snapshot.py          # 跨 run 失败分布漂移
│   └── compare_eval.py            # 同 run 跨 evaluator 对比
├── tests/                         # 无网络离线回归测试
├── batch_generate.py              # 生成入口
├── batch_evaluate.py              # 版本化评测 / replay / offline 入口
├── .env.example
├── pyproject.toml
└── README.md
```

运行产物：

```text
runs/run_xxx/
├── generated_results.jsonl
├── task_snapshot.jsonl
├── run_metadata.json
└── evaluations/
    └── eval_v0.3.0/
        ├── eval_results.jsonl
        ├── badcase_pool.jsonl
        ├── judge_failures.jsonl
        └── eval_metadata.json
```

核心依赖方向：

```text
batch_evaluate → Evaluator → metrics / ProsodyProfile → schema + data
```

批处理不直接调用 metrics。generation artifact 冻结，evaluator 输出按版本隔离。
