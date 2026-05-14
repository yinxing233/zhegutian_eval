# src/main.py

from schema.rule_config import load_rule_config


def main():
    rule = load_rule_config("rules/zhegutian_zhengti.json")

    print("=== 基本信息 ===")
    print(rule.cipai)
    print(rule.variant)
    print(rule.total_chars)

    print("\n=== 结构检查 ===")
    print(f"段数: {len(rule.stanzas)}")
    print(f"第一段句数: {len(rule.stanzas[0].lines)}")

    print("\n=== 第一行示例 ===")
    first_line = rule.stanzas[0].lines[0]
    print(first_line)

    # === 遍历整体结构 ===
    print("\n=== 全词结构遍历 ===")
    for stanza in rule.stanzas:
        print(f"\n== {stanza.section} ==")
        for line in stanza.lines:
            print(
                f"{line.index}: {line.text_tpl} | 字数={line.char_count} | 押韵={line.rhyme}"
            )

    # === 总字数校验 ===
    total = sum(line.char_count for s in rule.stanzas for line in s.lines)

    print("\n=== 总字数校验 ===")
    print("计算得到:", total)
    print("规则声明:", rule.total_chars)
    print("是否匹配:", total == rule.total_chars)


if __name__ == "__main__":
    main()