"""
生成→评测闭环脚本（增强版）
读取 data/eval_zhegutian.jsonl 中的样本，逐条生成并评测。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluator import Evaluator
from src.generator import create_generator
from src.schema.rule_config import load_rule_config

# 尝试导入 tabulate，若未安装则使用简单打印
try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# 生成词作时的固定追加指令（要求模型以 [END] 结尾，与 stop_sequences 配合）
GENERATION_SUFFIX = (
    "请严格只输出一首完整的词，不要任何说明、注释、标题、标点以外的符号，直接以正文开始。"
    "词作结束后另起一行输出 [END]。"
)


def main():
    # 1. 加载评测集
    eval_path = PROJECT_ROOT / "data" / "eval_zhegutian.jsonl"
    if not eval_path.exists():
        print(f"❌ 评测集不存在：{eval_path}")
        return
    samples = []
    with open(eval_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    print(f"📄 加载了 {len(samples)} 条评测样本")

    # 2. 加载鹧鸪天规则（后续可根据 cipai 动态加载）
    rule_path = PROJECT_ROOT / "rules" / "zhegutian_zhengti.json"
    rule = load_rule_config(rule_path)
    evaluator = Evaluator(rule)

    # 3. 初始化生成器
    gen = create_generator()

    # 4. 逐条评测
    results = []
    for sample in samples:
        sample_id = sample.get("id", "unknown")
        prompt = sample.get("prompt", "") + GENERATION_SUFFIX
        print(f"\n⚙️ 正在处理 {sample_id}...")

        # 生成
        ci_text = gen.generate(prompt)
        # 清洗模型输出的 [END] 标记，避免干扰评测
        ci_text = ci_text.replace("[END]", "").strip()
        # 打印前 100 字预览
        print(f"   生成文本：{ci_text[:100].replace(chr(10), ' ')}...")

        # 获取 finish_reason 用于诊断
        finish_reason = getattr(gen, "last_finish_reason", "UNKNOWN")

        # 判断各类生成 Bad Case
        is_badcase = False
        badcase_reason = ""

        if ci_text.startswith("[Error:") or ci_text.startswith("[API Error:"):
            is_badcase = True
            badcase_reason = ci_text
            # 直接记录并 continue，不进行评测
            results.append({...})
            continue
        else:
            # ---------- 截断与完整性自检 ----------
            if finish_reason == "MAX_TOKENS":
                # 二次确认：如果词作实际已完整（鹧鸪天 9 句），不算截断
                from src.utils import split_into_lines

                test_lines = split_into_lines(ci_text)
                if len(test_lines) == 9:
                    # 词已完整，不标记为截断
                    pass
                else:
                    is_badcase = True
                    badcase_reason = "因达到最大 token 限制而截断"
            elif len(ci_text) < 40:  # 鹧鸪天正常约 55-70 字符
                is_badcase = True
                badcase_reason = "文本长度异常（可能未写完）"

            # 进行评测（即使已经标记为截断，我们仍评分以查看部分质量）
            eval_result = evaluator.evaluate(ci_text, prompt_context=sample["prompt"])
            overall = eval_result["overall"]
            print(f"   ✅ 总分: {overall['total']} / 100")
            print(f"      结构: {overall['breakdown']['structure']}")
            print(f"      平仄: {overall['breakdown']['pingze']}")
            print(f"      押韵: {overall['breakdown']['rhyme']}")
            print(f"      对仗: {overall['breakdown']['antithesis']}")
            print(f"      语义: {overall['breakdown']['semantic']}")

            # 如果评测总分极低，也追加标记（但保留原有原因）
            if overall["total"] < 60.0 and not is_badcase:
                is_badcase = True
                badcase_reason = f"总分过低 ({overall['total']})"
            elif overall["total"] < 60.0 and is_badcase:
                badcase_reason += f" + 总分过低 ({overall['total']})"

            results.append(
                {
                    "id": sample_id,
                    "prompt": sample["prompt"],
                    "generated": ci_text,
                    "finish_reason": finish_reason,
                    "overall_total": overall["total"],
                    "breakdown": overall["breakdown"],
                    "is_badcase": is_badcase,
                    "badcase_reason": badcase_reason,
                }
            )
            continue  # 跳过后续的纯错误处理分支

        # 只有以 [Error: 开头的情况才会走到这里
        results.append(
            {
                "id": sample_id,
                "prompt": sample["prompt"],
                "generated": ci_text,
                "finish_reason": finish_reason,
                "overall_total": 0,
                "breakdown": {},
                "is_badcase": True,
                "badcase_reason": badcase_reason,
            }
        )

    # 5. 汇总输出
    print("\n" + "=" * 60)
    print("📊 评测汇总")
    table_data = []
    for r in results:
        breakdown = r.get("breakdown", {})
        table_data.append(
            [
                r["id"],
                r["overall_total"],
                breakdown.get("pingze", 0) if breakdown else 0,
                breakdown.get("rhyme", 0) if breakdown else 0,
                "⚠️" if r["is_badcase"] else "✅",
                r["badcase_reason"][:50] if r["badcase_reason"] else "",
                r.get("finish_reason", ""),
            ]
        )
    headers = ["ID", "总分", "平仄", "押韵", "状态", "原因", "Finish Reason"]
    if HAS_TABULATE:
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    else:
        # 简单格式化输出
        for row in table_data:
            print(" | ".join(str(x) for x in row))
        print("(提示: 安装 tabulate 可获得更美观的表格)")

    # 6. 保存详细结果
    output_path = PROJECT_ROOT / "eval_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📁 详细结果已保存至 {output_path}")


if __name__ == "__main__":
    main()
