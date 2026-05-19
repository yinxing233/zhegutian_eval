"""
ΔS 层：失败模式分布漂移分析工具
用法：python tools/delta_snapshot.py <run_dir_a> <run_dir_b>
输出两次实验之间 failure mode 的频次变化，并按 ΔD_task / ΔD_eval / ΔD_gen 标注漂移来源。
"""

import json
import sys
from collections import Counter
from pathlib import Path


def load_eval_results(run_dir: Path) -> list:
    path = run_dir / "eval_results.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}")
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def load_metadata(run_dir: Path) -> dict:
    path = run_dir / "run_metadata.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def extract_failure_modes(results: list) -> Counter:
    """从评测结果中提取所有 error_category 标签的频次"""
    modes = Counter()
    for r in results:
        for tag in r.get("error_category", []):
            modes[tag] += 1
    return modes


def main():
    if len(sys.argv) != 3:
        print("用法：python tools/delta_snapshot.py <run_dir_a> <run_dir_b>")
        sys.exit(1)

    dir_a = Path(sys.argv[1])
    dir_b = Path(sys.argv[2])

    results_a = load_eval_results(dir_a)
    results_b = load_eval_results(dir_b)
    meta_a = load_metadata(dir_a)
    meta_b = load_metadata(dir_b)

    modes_a = extract_failure_modes(results_a)
    modes_b = extract_failure_modes(results_b)

    all_modes = sorted(set(list(modes_a.keys()) + list(modes_b.keys())))

    # 检测 Δ 来源
    delta_sources = []
    if meta_a.get("gen_model") != meta_b.get("gen_model") or meta_a.get(
        "gen_provider"
    ) != meta_b.get("gen_provider"):
        delta_sources.append("ΔD_gen")
    if meta_a.get("judge_model") != meta_b.get("judge_model") or meta_a.get(
        "judge_provider"
    ) != meta_b.get("judge_provider"):
        delta_sources.append("ΔD_eval")
    if meta_a.get("task_dataset_hash") != meta_b.get("task_dataset_hash"):
        delta_sources.append("ΔD_task")
    if not delta_sources:
        delta_sources.append("ΔD_unknown")

    print("=" * 70)
    print("ΔS 失败模式漂移分析")
    print(f"  Run A: {dir_a.name}")
    print(f"  Run B: {dir_b.name}")
    print(f"  检测到的 Δ 来源: {', '.join(delta_sources)}")
    print("=" * 70)
    print(f"{'Failure Mode':<35} {'Run A':>8} {'Run B':>8} {'Δ':>8}")
    print("-" * 70)

    for mode in all_modes:
        count_a = modes_a.get(mode, 0)
        count_b = modes_b.get(mode, 0)
        delta = count_b - count_a
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        print(f"{mode:<35} {count_a:>8} {count_b:>8} {delta_str:>8}")

    # 简短解读
    print("\n📋 漂移解读：")
    increased = [
        (m, modes_b[m] - modes_a[m])
        for m in all_modes
        if modes_b.get(m, 0) > modes_a.get(m, 0)
    ]
    decreased = [
        (m, modes_a[m] - modes_b[m])
        for m in all_modes
        if modes_a.get(m, 0) > modes_b.get(m, 0)
    ]

    if increased:
        print("  ⬆️ 上升的失败模式：")
        for mode, delta in increased:
            print(f"     - {mode}: +{delta}")
    if decreased:
        print("  ⬇️ 下降的失败模式：")
        for mode, delta in decreased:
            print(f"     - {mode}: -{delta}")
    if not increased and not decreased:
        print("  ➡️ 失败模式分布无显著变化")


if __name__ == "__main__":
    main()
