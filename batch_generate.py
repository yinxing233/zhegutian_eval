"""
批量生成脚本
从 data/eval_zhegutian.jsonl 读取样本，逐条生成，
结果写入 runs/<run_id>/generated_results.jsonl（含完整实验快照）。
同时生成 run_metadata.json 和 task_snapshot.jsonl 冻结因果来源。

v3 更新：
- 使用可读 run_id（序号 + 时间戳 + 模型标识）
- 自动创建 runs/ 子目录，实现实验版本隔离
- 写入 run_metadata.json 冻结因果来源
- 写入 task_snapshot.jsonl 冻结输入任务集
- 路径安全：sanitize 模型名中的非法字符
- 保留 raw_output 字段，不丢失模型原始输出
- 冻结输入哈希 task_dataset_hash
- 修复 [END] 误伤清洗

v4 更新（MVP 重构）：
- 使用统一 clean_text() 替代零散清洗（通用卫生层）
- 低压 prompt suffix，移除对 [END] 的显式指令
- reasoning 不再污染正文（generator 层隔离）
- 按 provider 分流清洗：Gemini 仅最小清洗，GLM 附加正文提取
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from src.generator import create_generator
from utils.extractor import extract_ci_text
from utils.text_cleaner import clean_text

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

# ============================================================
# ProviderAdapter：隔离所有 provider 差异
# 每个 provider 有独立的 prompt_suffix 和 postprocess 函数
# ============================================================


def _identity(text: str) -> str:
    """不做任何后处理，直接透传"""
    return text


PROVIDER_CONFIG = {
    "gemini": {
        # Gemini 需要轻度指令防止它进入"先解释再写词"模式
        # 但不使用"严格""禁止"等高压词，避免触发审查态
        "prompt_suffix": "\n请直接写出这首词，不要任何说明、注释或背景介绍：\n",
        "postprocess": _identity,
    },
    "deepseek": {
        # DeepSeek 的 reasoning 已在 generator 层隔离
        # 低压 continuation 风格即可
        "prompt_suffix": "\n下面是一首《鹧鸪天》：\n",
        "postprocess": _identity,
    },
    "glm": {
        # GLM 输出 final_answer + self_explanation
        # 需要 extract_ci_text 提取正文
        "prompt_suffix": "\n下面是一首《鹧鸪天》：\n",
        "postprocess": extract_ci_text,
    },
}

# 默认配置（未知 provider 的回退）
DEFAULT_PROVIDER_CONFIG = {
    "prompt_suffix": "\n下面是一首《鹧鸪天》：\n",
    "postprocess": _identity,
}


def sanitize_name(name: str) -> str:
    """移除路径非法字符，避免 Windows / Linux 路径崩溃"""
    return re.sub(r"[^a-zA-Z0-9._-]", "-", name)


def normalize_sample(sample: dict) -> dict:
    """将旧格式样本统一升级为新 schema，保证系统内部只有一种格式"""
    return {
        "task_id": sample.get("task_id") or sample.get("id", "unknown"),
        "L0_surface_prompt": sample.get("L0_surface_prompt")
        or sample.get("prompt", ""),
        "L0_constraints": sample.get("L0_constraints", {}),
        "L0_difficulty_axes": sample.get("L0_difficulty_axes", {}),
        "L0_task_tags": sample.get("L0_task_tags", []),
        "L1_expected_failure_modes": sample.get("L1_expected_failure_modes", []),
        "L2_latent_tensions": sample.get("L2_latent_tensions", []),
        "prompt_version": sample.get("prompt_version", "unknown"),
    }


def main():
    input_path = PROJECT_ROOT / "data" / "eval_zhegutian.jsonl"

    if not input_path.exists():
        print(f"❌ 输入文件不存在：{input_path}")
        return

    raw_samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_samples.append(json.loads(line))

    # 入口统一 normalize，消除新旧格式混合
    samples = [normalize_sample(s) for s in raw_samples]
    print(f"📄 加载了 {len(samples)} 条生成提示（已统一 schema）")

    gen = create_generator()
    gen_provider = os.getenv("LLM_PROVIDER", "unknown")
    gen_model = gen.model_name
    temperature = gen.temperature
    max_tokens = gen.max_output_tokens
    delay = float(os.getenv("API_DELAY_SECONDS", "0"))

    # 获取当前 provider 的配置
    provider_cfg = PROVIDER_CONFIG.get(gen_provider.lower(), DEFAULT_PROVIDER_CONFIG)
    prompt_suffix = provider_cfg["prompt_suffix"]
    postprocess = provider_cfg["postprocess"]

    print(f"🔧 Provider: {gen_provider} | suffix: {prompt_suffix.strip()}")

    # ----- 构建实验运行目录与唯一 ID -----
    runs_base = PROJECT_ROOT / "runs"
    runs_base.mkdir(parents=True, exist_ok=True)

    # 自动编号（注：此方法在单进程下安全，并发场景需引入文件锁或原子计数器）
    existing_runs = [
        d.name for d in runs_base.iterdir() if d.is_dir() and d.name.startswith("run_")
    ]
    max_num = 0
    for name in existing_runs:
        try:
            num = int(name.split("_")[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            pass
    run_num = max_num + 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    judge_provider = os.getenv("EVAL_PROVIDER", "unknown")
    judge_model = os.getenv("EVAL_MODEL", "unknown")

    # 路径安全：sanitize 模型名
    safe_gen_model = sanitize_name(gen_model)
    safe_judge_model = sanitize_name(judge_model)
    run_id = (
        f"run_{run_num:03d}_{timestamp}_"
        f"{gen_provider}-{safe_gen_model}_"
        f"{judge_provider}-{safe_judge_model}"
    )
    run_dir = runs_base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    output_path = run_dir / "generated_results.jsonl"

    # ----- 计算输入任务集哈希 -----
    task_dataset_hash = hashlib.md5(
        json.dumps(samples, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]

    # ----- 生成 run_metadata.json -----
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:
        git_commit = "unknown"

    metadata = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "gen_model": gen_model,
        "gen_provider": gen_provider,
        "judge_model": judge_model,
        "judge_provider": judge_provider,
        "prompt_version": "v4-provider-adapter",
        "git_commit": git_commit,
        "parent_run": None,
        "description": "",
        "task_dataset_hash": task_dataset_hash,
    }
    with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # ----- 逐条生成 -----
    batch_run_id = run_id

    results = []
    for idx, sample in enumerate(samples):
        task_id = sample["task_id"]
        surface_prompt = sample["L0_surface_prompt"]
        prompt_version = sample["prompt_version"]

        # Provider 自适应 prompt
        full_prompt = surface_prompt + prompt_suffix
        print(f"⚙️ [{idx + 1}/{len(samples)}] 生成 {task_id} ...")

        raw_output = gen.generate(full_prompt)

        # 通用卫生层（所有 provider）
        cleaned = clean_text(raw_output)

        # Provider 特定的后处理
        ci_text = postprocess(cleaned)

        finish_reason = getattr(gen, "last_finish_reason", "UNKNOWN")
        print(f"   finish_reason: {finish_reason}")

        record = {
            # 实验身份
            "batch_run_id": batch_run_id,
            "task_id": task_id,
            "task_sample_id": f"{task_id}__{batch_run_id}",
            "prompt_version": prompt_version,
            "model": gen_model,
            "provider": gen_provider,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            # 生成结果
            "raw_output": raw_output,
            "generated": ci_text,
            "finish_reason": finish_reason,
            # 内容来源追踪
            "content_source": getattr(gen, "last_content_source", None),
            "reasoning_content": getattr(gen, "last_reasoning_content", None),
            # 透传任务层（给评测阶段用）
            "L0_surface_prompt": surface_prompt,
            "L0_constraints": sample["L0_constraints"],
            "L0_difficulty_axes": sample["L0_difficulty_axes"],
            "L0_task_tags": sample["L0_task_tags"],
            "L1_expected_failure_modes": sample["L1_expected_failure_modes"],
            "L2_latent_tensions": sample["L2_latent_tensions"],
        }
        results.append(record)

        if delay > 0 and idx < len(samples) - 1:
            time.sleep(delay)

    # 写入生成结果
    with open(output_path, "w", encoding="utf-8") as f:
        for record in results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ----- 冻结本次使用的任务集快照（输入快照，关键用于 ΔS 分析）-----
    task_snapshot_path = run_dir / "task_snapshot.jsonl"
    with open(task_snapshot_path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"\n✅ 生成完毕，共 {len(results)} 条")
    print(f"   run_id: {run_id}")
    print(f"   结果已保存至 {output_path}")
    print(f"   任务集快照已保存至 {task_snapshot_path}")
    print(f"   实验目录: {run_dir}")


if __name__ == "__main__":
    main()
