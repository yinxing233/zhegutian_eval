"""
批量评测脚本
从指定的 run 目录（或最新 run）读取 generated_results.jsonl，逐条评测，
输出完整实验快照到同一 run 目录下的 eval_results.jsonl，
同时将 badcase 和 judge 故障写入该 run 目录。

支持命令行参数：
  python batch_evaluate.py --run run_xxx    # 显式指定 run
  python batch_evaluate.py                  # 默认使用最新的 run

v3 更新：
- 使用 runs/ 目录结构，输入输出均落在同一 run 目录内
- 增加 resolve_run_dir() 支持显式或自动选择 run
- 与 batch_generate.py 配合，形成完整实验快照
- 输出格式改为 jsonl
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.evaluator import Evaluator
from src.schema.rule_config import load_rule_config

try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

load_dotenv()


def resolve_run_dir(run_id: Optional[str] = None) -> Path:
    """解析 run 目录。若指定 run_id，使用对应目录；否则自动选择 runs/ 下最新的。"""
    runs_base = PROJECT_ROOT / "runs"
    if not runs_base.exists():
        raise FileNotFoundError("runs/ 目录不存在，请先运行 batch_generate.py")

    if run_id:
        target = runs_base / run_id
        if not target.exists():
            raise FileNotFoundError(f"指定的 run 目录不存在：{target}")
        return target

    # 默认：按 run_id 名称排序取最新
    def extract_run_num(p: Path) -> int:
        try:
            return int(p.name.split("_")[1])
        except:
            return -1

    all_runs = sorted(
        [d for d in runs_base.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=extract_run_num,
        reverse=True,
    )
    if not all_runs:
        raise FileNotFoundError("runs/ 目录为空")
    return all_runs[0]


def main():
    # 解析命令行参数
    run_id = None
    if "--run" in sys.argv:
        idx = sys.argv.index("--run")
        if idx + 1 < len(sys.argv):
            run_id = sys.argv[idx + 1]

    try:
        run_dir = resolve_run_dir(run_id)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    generated_file = run_dir / "generated_results.jsonl"
    if not generated_file.exists():
        print(f"❌ 在 {run_dir} 中找不到 generated_results.jsonl")
        return

    output_path = run_dir / "eval_results.jsonl"
    badcase_path = run_dir / "badcase_pool.jsonl"
    judge_failure_path = run_dir / "judge_failures.jsonl"

    print(f"📂 使用运行目录：{run_dir}")

    records = []
    with open(generated_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"📄 读取到 {len(records)} 条生成记录")

    rule_path = PROJECT_ROOT / "rules" / "zhegutian_zhengti.json"
    rule = load_rule_config(rule_path)

    STRUCTURE_FULL = 10.0
    RHYME_FULL = 20.0
    STRUCTURE_RHYME_THRESHOLD_RATIO = float(
        os.getenv("STRUCTURE_RHYME_THRESHOLD_RATIO", "0.8")
    )
    MIN_PINGZE_FOR_SEMANTIC = float(os.getenv("MIN_PINGZE_FOR_SEMANTIC", "20"))

    delay = float(os.getenv("API_DELAY_SECONDS", "0"))

    evaluator = Evaluator(rule)
    judge_model = os.getenv("EVAL_MODEL", "unknown")
    judge_provider = os.getenv("EVAL_PROVIDER", "unknown")
    eval_version = "v0.2.2"

    dimension_max = {
        "structure": 10,
        "pingze": 30,
        "rhyme": 20,
        "antithesis": 20,
        "semantic": 20,
    }

    results = []
    for idx, record in enumerate(records):
        task_id = record.get("task_id", f"record_{idx}")
        ci_text = record.get("generated", "")
        prompt_context = record.get("L0_surface_prompt", "")
        constraints = record.get("L0_constraints", {})
        finish_reason = record.get("finish_reason", "UNKNOWN")

        print(f"🔍 [{idx + 1}/{len(records)}] 评测 {task_id} ...")

        # 只做一次本地评测（格律部分）
        eval_result = evaluator.evaluate(
            ci_text,
            prompt_context=prompt_context,
            skip_semantic=True,
            constraints=constraints,
        )
        breakdown = eval_result["overall"]["breakdown"]
        structure_score = breakdown["structure"]
        rhyme_score = breakdown["rhyme"]
        pingze_score = breakdown["pingze"]

        # 判断是否触发 LLM 语义评测
        do_semantic = (
            structure_score >= STRUCTURE_FULL * STRUCTURE_RHYME_THRESHOLD_RATIO
            and rhyme_score >= RHYME_FULL * STRUCTURE_RHYME_THRESHOLD_RATIO
            and pingze_score > MIN_PINGZE_FOR_SEMANTIC
        )

        # 初始化语义结果为占位对象（避免后续访问 NameError）
        semantic_result = {
            "success": False,
            "score": None,
            "error_type": "not_evaluated",
            "raw": "",
        }
        missing_reason = {}

        if do_semantic:
            print("   → 触发 LLM 语义评测")
            semantic_result = evaluator.evaluate_semantic_only(ci_text, prompt_context)

            if semantic_result.get("success"):
                semantic_score = round(semantic_result["score"] * 20, 2)
                semantic_evaluated = True
                evaluated_dims = [
                    "structure",
                    "pingze",
                    "rhyme",
                    "antithesis",
                    "semantic",
                ]
            else:
                semantic_score = None
                semantic_evaluated = False
                evaluated_dims = ["structure", "pingze", "rhyme", "antithesis"]
                error_type = semantic_result.get("error_type", "unknown")
                missing_reason["semantic"] = f"judge_fail:{error_type}"

                # 追加裁判故障记录
                judge_failure_path.parent.mkdir(parents=True, exist_ok=True)
                with open(judge_failure_path, "a", encoding="utf-8") as jf:
                    failure_record = {
                        "timestamp": datetime.now().isoformat(),
                        "task_id": task_id,
                        "judge_model": judge_model,
                        "provider": judge_provider,
                        "error_type": error_type,
                        "raw": semantic_result.get("raw", "")[:500],
                    }
                    jf.write(json.dumps(failure_record, ensure_ascii=False) + "\n")
        else:
            semantic_score = None
            semantic_evaluated = False
            evaluated_dims = ["structure", "pingze", "rhyme", "antithesis"]
            missing_reason["semantic"] = "rule_skip"

        # 组装指标
        metrics = {
            "structure": structure_score,
            "pingze": pingze_score,
            "rhyme": rhyme_score,
            "antithesis": breakdown.get("antithesis", 0),
            "semantic": semantic_score,
        }

        valid_scores = {k: v for k, v in metrics.items() if v is not None}
        coverage = len(valid_scores) / len(metrics)

        total_score = round(sum(valid_scores.values()), 2)
        available_score = sum(dimension_max[k] for k in valid_scores)
        normalized_score = (
            round(total_score / available_score * 100, 2) if available_score > 0 else 0
        )

        # 传入 reasoning_content 诊断 reasoning_overflow
        reasoning_content = record.get("reasoning_content")
        error_tags_raw = Evaluator.infer_instability_pattern(
            metrics, ci_text, finish_reason, reasoning_content
        )
        error_category = [tag["symptom"] for tag in error_tags_raw]

        # 追加生成截断标记
        if (
            finish_reason == "MAX_TOKENS"
            and "generation_truncated" not in error_category
        ):
            error_category = ["generation_truncated"] + [
                t for t in error_category if t != "generation_truncated"
            ]

        is_badcase = (
            normalized_score < 60
            or len(error_category) > 0
            or ci_text.startswith("[Error:")
            or ci_text.startswith("[API Error:")
            or finish_reason == "MAX_TOKENS"
        )
        badcase_reason = "; ".join(error_category) if error_category else ""

        snapshot = {
            "batch_run_id": record.get("batch_run_id", run_dir.name),
            "task_id": task_id,
            "task_sample_id": record.get("task_sample_id", f"{task_id}__eval_{idx}"),
            "prompt_version": record.get("prompt_version", "unknown"),
            "model": record.get("model", "unknown"),
            "provider": record.get("provider", "unknown"),
            "temperature": record.get("temperature", 0),
            "max_output_tokens": record.get("max_output_tokens", 0),
            "judge_model": judge_model,
            "judge_provider": judge_provider,
            "eval_version": eval_version,
            "timestamp": datetime.now().isoformat(),
            "L0_task_tags": record.get("L0_task_tags", []),
            "L0_difficulty_axes": record.get("L0_difficulty_axes", {}),
            "L1_expected_failure_modes": record.get("L1_expected_failure_modes", []),
            "generated": ci_text,
            "finish_reason": finish_reason,
            "metrics": metrics,
            "evaluated_dimensions": evaluated_dims,
            "coverage": round(coverage, 2),
            "missing_dimensions": [k for k, v in metrics.items() if v is None],
            "missing_reason": missing_reason if missing_reason else None,
            "semantic_evaluated": semantic_evaluated,
            "total_score": total_score,
            "available_score": available_score,
            "normalized_score": normalized_score,
            "error_category": error_category,
            "instability_tags": error_tags_raw,  # ← 新增结构化标签
            "badcase": is_badcase,
            "badcase_reason": badcase_reason,
            "semantic_raw": semantic_result.get("raw", "")[:500],
            "failure_trace": eval_result.get("failure_trace", []),
        }
        results.append(snapshot)

        if is_badcase:
            badcase_path.parent.mkdir(parents=True, exist_ok=True)
            with open(badcase_path, "a", encoding="utf-8") as bf:
                bf.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

        if do_semantic and semantic_evaluated and delay > 0:
            time.sleep(delay)

    # 汇总输出
    print("\n" + "=" * 60)
    print("📊 评测汇总")
    table_data = []
    for r in results:
        sem_display = r["metrics"]["semantic"]
        if sem_display is None:
            if r.get("missing_reason") and "semantic" in r["missing_reason"]:
                reason_short = r["missing_reason"]["semantic"]
                sem_display = f"跳过({reason_short[:12]})"
            else:
                sem_display = "未评"

        error_tags = list(r["error_category"]) if r["error_category"] else []
        finish = r.get("finish_reason", "")
        if finish == "MAX_TOKENS" and "generation_truncated" not in error_tags:
            error_tags.insert(0, "generation_truncated")

        norm_display = f"{r['normalized_score']:.1f}"
        if r["coverage"] < 1.0:
            norm_display += " ⚠️"

        table_data.append(
            [
                r["task_id"],
                norm_display,
                f"{r['coverage']:.0%}",
                r["metrics"]["pingze"] if r["metrics"]["pingze"] is not None else "-",
                r["metrics"]["rhyme"] if r["metrics"]["rhyme"] is not None else "-",
                sem_display,
                ", ".join(error_tags) if error_tags else "✅",
                finish,
            ]
        )
    headers = ["ID", "归一化分", "覆盖率", "平仄", "押韵", "语义", "诊断", "Finish"]
    if HAS_TABULATE:
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    else:
        for row in table_data:
            print(" | ".join(str(x) for x in row))

    with open(output_path, "w", encoding="utf-8") as f:
        for snapshot in results:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(f"\n📁 详细结果已保存至 {output_path}")
    print(f"📁 Bad Case 池已追加至 {badcase_path}")
    if judge_failure_path.exists():
        print(f"📁 裁判故障记录已追加至 {judge_failure_path}")


if __name__ == "__main__":
    main()
