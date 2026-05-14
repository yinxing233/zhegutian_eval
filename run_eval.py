# run_eval.py
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schema.rule_config import load_rule_config
from src.evaluator import Evaluator

# 内置样例词作（可手动切换 SELECTED 或通过命令行选择）
SAMPLES = {
    "mine": {
        "desc": "yinxing233《鹧鸪天·述怀》",
        "text": (
            "云淡星微皎月环，初心未改世间难。"
            "心存寰宇灵思阔，身历炎凉天地宽。"
            "词作了，羡诗仙，纵情山水有名篇。"
            "文章未必逢悲苦，情至方得永世传。"
        )
    },
    "yanshu": {
        "desc": "晏殊《鹧鸪天·彩袖殷勤捧玉钟》",
        "text": (
            "彩袖殷勤捧玉钟，当年拚却醉颜红。"
            "舞低杨柳楼心月，歌尽桃花扇影风。"
            "从别后，忆相逢，几回魂梦与君同。"
            "今宵剩把银釭照，犹恐相逢是梦中。"
        )
    },
    "xinqiji": {
        "desc": "辛弃疾《鹧鸪天·送人》",
        "text": (
            "唱彻阳关泪未干，功名馀事且加餐。"
            "浮天水送无穷树，带雨云埋一半山。"
            "今古恨，几千般，只应离合是悲欢。"
            "江头未是风波恶，别有人间行路难。"
        )
    }
}

# 默认使用自撰词（展示检错能力），也可改为 "yanshu" 等
SELECTED = "mine"

def main():
    if len(sys.argv) > 1 and sys.argv[1] in SAMPLES:
        key = sys.argv[1]
    else:
        key = SELECTED

    sample = SAMPLES[key]
    print(f"▶ 当前评测样例：{sample['desc']}")
    ci_text = sample["text"]

    rule_path = PROJECT_ROOT / "rules" / "zhegutian_zhengti.json"
    rule = load_rule_config(rule_path)
    evaluator = Evaluator(rule)
    result = evaluator.evaluate(ci_text)

    print("=" * 60)
    print(f"总分: {result['overall']['total']} / {result['overall']['max_total']}")
    print("-" * 60)
    for dim, score in result['overall']['breakdown'].items():
        print(f"  {dim}: {score}")
    print("=" * 60)

    # 可选：输出完整JSON
    # print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()