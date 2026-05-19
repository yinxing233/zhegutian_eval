# 项目架构 / Project Architecture

```markdown
zhegutian-eval/
├── .env # API Key 和生成参数（不进入版本控制）
├── data/
│ └── zhonghua_xinyun.json # 中华新韵韵部映射表
├── rules/
│ └── zhegutian_zhengti.json # 《鹧鸪天》正体格律规则（已定稿）
├── src/
│ ├── metrics/
│ │ ├── antithesis.py # 对仗检查（LLM-based，缺陷检测模式）
│ │ ├── pingze.py # 平仄检查（确定性规则）
│ │ ├── rhyme.py # 押韵检查（基于中华新韵）
│ │ └── semantic.py # 语义/意境检查（LLM-based，缺陷检测模式）
│ ├── schema/
│ │ ├── **init**.py
│ │ └── rule_config.py # 规则结构定义（强类型对象）
│ ├── **init**.py
│ ├── evaluator.py # 评测调度层（100分制，5维度）
│ ├── generator.py # 大模型生成层（当前支持 Gemini，DeepSeek,GLM，策略+工厂模式）
│ ├── llm_client.py # 统一 LLM 调用客户端（用于评测模块）
│ ├── main.py # 程序入口
│ └── utils.py # 文本清洗、断句、拼音/声调提取（纯工具）
├── tools/
│ └── delta_snapshot.py # 增量快照工具
├── batch_evaluate.py # 批量评测脚本
├── batch_generate.py # 批量生成脚本
├── pyproject.toml # uv 项目文件
└── uv.lock
```
