"""对冻结生成快照执行可版本化、可回放的批量评测。"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.evaluator import DIMENSION_MAX, EVAL_VERSION, Evaluator
from src.schema.rule_config import load_rule_config

try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

load_dotenv()


HARD_FAILURES = {
    "reasoning_overflow",
    "empty_output",
    "truncated",
    "structure_incomplete",
    "tone_fail",
    "rhyme_fail",
    "template_parroting",
    "aesthetic_entropy",
    "fragmentation",
    "constraint_violation",
}


def resolve_run_dir(run_id: Optional[str] = None) -> Path:
    """解析 run 目录；未指定时选择编号最大的 run。"""
    runs_base = PROJECT_ROOT / "runs"
    if not runs_base.exists():
        raise FileNotFoundError("runs/ 目录不存在，请先运行 batch_generate.py")

    if run_id:
        target = runs_base / run_id
        if not target.is_dir():
            raise FileNotFoundError(f"指定的 run 目录不存在：{target}")
        return target

    def extract_run_num(path: Path) -> int:
        try:
            return int(path.name.split("_")[1])
        except (IndexError, ValueError):
            return -1

    runs = [
        path
        for path in runs_base.iterdir()
        if path.is_dir() and path.name.startswith("run_")
        and (path / "generated_results.jsonl").exists()
    ]
    if not runs:
        raise FileNotFoundError("runs/ 目录为空")
    return max(runs, key=extract_run_num)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, "r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} 第 {line_number} 行不是合法 JSON") from exc
    return records


def _atomic_write_text(path: Path, content: str) -> None:
    """在目标目录内写临时文件，成功后原子替换旧产物。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as stream:
            temp_name = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def atomic_write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    )
    _atomic_write_text(path, content)


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def collect_judge_failures(
    result: Dict[str, Any],
    task_id: str,
    judge_model: str,
    judge_provider: str,
) -> List[Dict[str, Any]]:
    failures = []
    timestamp = datetime.now().isoformat()
    for item in result.get("antithesis", []):
        if not item.get("success", False):
            failures.append(
                {
                    "timestamp": timestamp,
                    "task_id": task_id,
                    "dimension": "antithesis",
                    "sentence_pair": item.get("sentence_pair"),
                    "judge_model": judge_model,
                    "provider": judge_provider,
                    "error_type": item.get("error_type", "unknown"),
                    "raw": item.get("raw", "")[:500],
                }
            )
    semantic = result.get("semantic", {})
    if result.get("llm_evaluation_triggered") and not semantic.get("success", False):
        failures.append(
            {
                "timestamp": timestamp,
                "task_id": task_id,
                "dimension": "semantic",
                "judge_model": judge_model,
                "provider": judge_provider,
                "error_type": semantic.get("error_type", "unknown"),
                "raw": semantic.get("raw", "")[:500],
            }
        )
    return failures


def evaluate_record(
    evaluator: Evaluator,
    record: Dict[str, Any],
    index: int,
    run_dir: Path,
    judge_model: str,
    judge_provider: str,
    threshold_ratio: float,
    min_pingze: float,
    enable_llm: bool,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    task_id = record.get("task_id", f"record_{index}")
    ci_text = record.get("generated", "")
    finish_reason_raw = record.get("finish_reason", "unknown")
    finish_reason = evaluator.normalize_finish_reason(finish_reason_raw)

    result = evaluator.evaluate_conditional(
        ci_text,
        prompt_context=record.get("L0_surface_prompt", ""),
        constraints=record.get("L0_constraints", {}),
        structure_rhyme_threshold_ratio=threshold_ratio,
        min_pingze_for_llm=min_pingze,
        enable_llm=enable_llm,
    )

    breakdown = result["overall"]["breakdown"]
    metrics = {name: breakdown.get(name) for name in DIMENSION_MAX}
    instability_tags = evaluator.infer_instability_pattern(
        metrics,
        generated=ci_text,
        finish_reason=finish_reason,
        reasoning_content=record.get("reasoning_content"),
    )
    if result.get("constraint_violations"):
        instability_tags.append(
            {"symptom": "constraint_violation", "primary_field": "M_ONLY"}
        )

    error_category = list(dict.fromkeys(tag["symptom"] for tag in instability_tags))
    hard_failures = [name for name in error_category if name in HARD_FAILURES]
    normalized_score = result["overall"]["normalized_score"]
    provider_error = ci_text.startswith(("[Error:", "[API Error:"))
    is_badcase = normalized_score < 60 or bool(hard_failures) or provider_error

    reasons = list(hard_failures)
    if normalized_score < 60:
        reasons.append("normalized_score_below_60")
    if provider_error:
        reasons.append("provider_error")

    # 从生成快照复制完整因果来源，再叠加当前 evaluator 的解释。
    snapshot = dict(record)
    snapshot.update(
        {
            "batch_run_id": record.get("batch_run_id", run_dir.name),
            "task_id": task_id,
            "task_sample_id": record.get(
                "task_sample_id", f"{task_id}__eval_{index}"
            ),
            "judge_model": judge_model,
            "judge_provider": judge_provider,
            "eval_version": EVAL_VERSION,
            "eval_timestamp": datetime.now().isoformat(),
            "prosody_profile": result["prosody_profile"],
            "finish_reason_raw": finish_reason_raw,
            "finish_reason": finish_reason,
            "metrics": metrics,
            "dimension_status": result["dimension_status"],
            "evaluated_dimensions": [
                name
                for name, status in result["dimension_status"].items()
                if status == "valid"
            ],
            "coverage": result["overall"]["coverage"],
            "missing_dimensions": result["missing_dimensions"],
            "missing_reason": result["missing_reason"],
            "constraint_violations": result["constraint_violations"],
            "llm_evaluation_triggered": result["llm_evaluation_triggered"],
            "total_score": result["overall"]["total"],
            "available_score": result["overall"]["available_score"],
            "normalized_score": normalized_score,
            "error_category": error_category,
            "instability_tags": instability_tags,
            "badcase": is_badcase,
            "badcase_reason": "; ".join(dict.fromkeys(reasons)),
            "semantic_raw": result.get("semantic", {}).get("raw", "")[:500],
            "failure_trace": result["failure_trace"],
        }
    )
    failures = collect_judge_failures(
        result, task_id, judge_model, judge_provider
    )
    return snapshot, failures


def print_summary(results: List[Dict[str, Any]]) -> None:
    rows = []
    for result in results:
        semantic = result["metrics"]["semantic"]
        if semantic is None:
            semantic = f"缺失({result['dimension_status']['semantic']})"
        rows.append(
            [
                result["task_id"],
                f"{result['normalized_score']:.1f}",
                f"{result['coverage']:.0%}",
                result["metrics"]["pingze"],
                result["metrics"]["rhyme"],
                semantic,
                ", ".join(result["error_category"]) or "未发现已知失稳",
                result["finish_reason"],
            ]
        )
    headers = ["ID", "归一化分", "覆盖率", "平仄", "押韵", "语义", "诊断", "Finish"]
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="grid"))
    else:
        for row in rows:
            print(" | ".join(str(value) for value in row))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="指定 runs/ 下的 run 目录名")
    parser.add_argument(
        "--replay", action="store_true", help="明确标记本次为冻结生成集回放"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="只运行确定性指标，不调用对仗/语义裁判",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_dir = resolve_run_dir(args.run)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 2

    generated_path = run_dir / "generated_results.jsonl"
    if not generated_path.exists():
        print(f"[ERROR] 在 {run_dir} 中找不到 generated_results.jsonl")
        return 2

    try:
        records = load_jsonl(generated_path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] 读取生成快照失败：{exc}")
        return 2

    eval_dir = run_dir / "evaluations" / f"eval_{EVAL_VERSION}"
    output_path = eval_dir / "eval_results.jsonl"
    badcase_path = eval_dir / "badcase_pool.jsonl"
    judge_failure_path = eval_dir / "judge_failures.jsonl"
    metadata_path = eval_dir / "eval_metadata.json"

    mode = "Replay" if args.replay else "Evaluation"
    print(f"[INFO] [{mode}] 冻结生成快照：{generated_path}")
    print(f"[INFO] 评测输出版本：{eval_dir}")
    if output_path.exists():
        print("[WARN] 当前 evaluator 版本结果已存在；成功完成后将原子替换该版本")

    threshold_ratio = float(
        os.getenv("STRUCTURE_RHYME_THRESHOLD_RATIO", "0.8")
    )
    min_pingze = float(os.getenv("MIN_PINGZE_FOR_SEMANTIC", "20"))
    delay = float(os.getenv("API_DELAY_SECONDS", "0"))
    judge_model = os.getenv("EVAL_MODEL", "unknown")
    judge_provider = os.getenv("EVAL_PROVIDER", "unknown")

    evaluator = Evaluator(
        load_rule_config(PROJECT_ROOT / "rules" / "zhegutian_zhengti.json")
    )
    results: List[Dict[str, Any]] = []
    judge_failures: List[Dict[str, Any]] = []

    for index, record in enumerate(records):
        task_id = record.get("task_id", f"record_{index}")
        print(f"[INFO] [{index + 1}/{len(records)}] 评测 {task_id} ...")
        snapshot, failures = evaluate_record(
            evaluator=evaluator,
            record=record,
            index=index,
            run_dir=run_dir,
            judge_model=judge_model,
            judge_provider=judge_provider,
            threshold_ratio=threshold_ratio,
            min_pingze=min_pingze,
            enable_llm=not args.offline,
        )
        results.append(snapshot)
        judge_failures.extend(failures)
        if snapshot["llm_evaluation_triggered"] and delay > 0:
            time.sleep(delay)

    badcases = [result for result in results if result["badcase"]]
    source_files = [
        PROJECT_ROOT / "src" / "evaluator.py",
        PROJECT_ROOT / "src" / "prosody.py",
        PROJECT_ROOT / "src" / "metrics" / "pingze.py",
        PROJECT_ROOT / "src" / "metrics" / "rhyme.py",
        PROJECT_ROOT / "src" / "metrics" / "antithesis.py",
        PROJECT_ROOT / "src" / "metrics" / "semantic.py",
        PROJECT_ROOT / "data" / "zhonghua_xinyun.json",
        PROJECT_ROOT / "rules" / "zhegutian_zhengti.json",
    ]
    metadata = {
        "eval_version": EVAL_VERSION,
        "timestamp": datetime.now().isoformat(),
        "source_generation_snapshot": str(generated_path.relative_to(PROJECT_ROOT)),
        "generation_snapshot_sha256": hashlib.sha256(
            generated_path.read_bytes()
        ).hexdigest(),
        "evaluator_sha256": sha256_files(source_files),
        "judge_model": judge_model,
        "judge_provider": judge_provider,
        "offline": args.offline,
        "structure_rhyme_threshold_ratio": threshold_ratio,
        "min_pingze_for_llm": min_pingze,
        "prosody_profiles": sorted(
            {result["prosody_profile"] for result in results}
        ),
        "record_count": len(results),
        "badcase_count": len(badcases),
        "judge_failure_count": len(judge_failures),
    }

    # 所有计算成功后才逐个原子替换；旧版本目录和历史根目录产物均不触碰。
    atomic_write_jsonl(output_path, results)
    atomic_write_jsonl(badcase_path, badcases)
    atomic_write_jsonl(judge_failure_path, judge_failures)
    atomic_write_json(metadata_path, metadata)

    print_summary(results)
    print(f"\n[OK] 评测完成：{len(results)} 条，badcase {len(badcases)} 条")
    print(f"[INFO] 结果：{output_path}")
    print(f"[INFO] 元数据：{metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
