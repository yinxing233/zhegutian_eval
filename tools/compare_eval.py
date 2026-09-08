"""比较同一 generation snapshot 的两个 evaluator 版本。

用法：
python tools/compare_eval.py --run runs/run_xxx --a v0.2.2 --b v0.3.0
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def load_results(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    results = {}
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                record = json.loads(line)
                results[record["task_id"]] = record
    return results


def version_path(run_dir: Path, version: str) -> Path:
    normalized = version if version.startswith("eval_") else f"eval_{version}"
    candidate = run_dir / "evaluations" / normalized / "eval_results.jsonl"
    if candidate.exists():
        return candidate
    # v0.2.x 及更早版本保存在 run 根目录。
    legacy = run_dir / "eval_results.jsonl"
    if legacy.exists():
        sample = next(iter(load_results(legacy).values()), {})
        if sample.get("eval_version") == version:
            return legacy
    raise FileNotFoundError(f"找不到 evaluator {version} 的结果")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    args = parser.parse_args()

    try:
        left = load_results(version_path(args.run, args.a))
        right = load_results(version_path(args.run, args.b))
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 2

    task_ids = sorted(set(left) | set(right))
    print(f"{'Task':<28} {'Score A':>9} {'Score B':>9} {'Δ':>9}  Badcase A→B")
    print("-" * 78)
    for task_id in task_ids:
        a = left.get(task_id)
        b = right.get(task_id)
        if not a or not b:
            print(f"{task_id:<28} {'missing':>9} {'missing':>9}")
            continue
        score_a = float(a.get("normalized_score", 0))
        score_b = float(b.get("normalized_score", 0))
        print(
            f"{task_id:<28} {score_a:>9.2f} {score_b:>9.2f} "
            f"{score_b - score_a:>+9.2f}  {a.get('badcase')}→{b.get('badcase')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
