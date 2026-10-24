#!/usr/bin/env python3
"""提纯：把完整调研结果压缩成适合飞书推送的精简摘要。

设计原则：仓库里存完整版（可查重、可追溯），飞书只推「这次有什么变化」。
推送内容不是报告的复述，而是决策信息——新增了什么、什么失效了、额度变了多少。

用法：
    python3 scripts/distill.py data/snapshots/2026-10-23-evening.md
    python3 scripts/distill.py data/snapshots/2026-10-23-evening.md --json   # 供推送脚本消费

输入快照需包含四节（新增 / 失效清单 / 额度变化 / 复检结果），
缺节时按「无」处理；若一节都没匹配到，则向 stderr 报诊断并以非 0 退出
（该文件不是任务 1 的四段式快照，请手写摘要推送）。
输出为纯文本，控制在 ~800 字内。
"""
import argparse
import json
import os
import re
import sys

MAX_CHARS = 900
SECTIONS = ("新增", "失效清单", "额度变化", "复检结果")


def parse_snapshot(path):
    """把快照 markdown 拆成 {节名: [行...]}。"""
    text = open(path, encoding="utf-8").read()
    out = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s*(?:[一二三四五六七八九十]+、)?\s*(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            current = title if any(s in title for s in SECTIONS) else None
            if current:
                out.setdefault(current, [])
            continue
        if current is not None:
            out[current].append(line.rstrip())
    return out


def extract_title(source):
    """标题优先取源文件自身的 H1（首个 '# ' 行），取不到则退回文件名。

    不附加任何字面前缀——不同任务的报告共用本脚本，硬编码前缀会张冠李戴。
    """
    try:
        text = open(source, encoding="utf-8").read()
    except OSError:
        text = ""
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return os.path.basename(source).replace(".md", "")


def is_table_noise(s):
    """表格分隔行、纯符号行。"""
    s = s.strip()
    return not s or bool(re.fullmatch(r"[|\s\-:]+", s))


def is_table_row(s):
    """是否是表格数据行（含未被替换的竖线）。"""
    return "|" in s and not is_table_noise(s)


def is_table_sep(s):
    """markdown 表格分隔行，如 |---|---| 或 --- | ---。"""
    return bool(re.fullmatch(r"\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*", s))


def strip_table_header(items):
    """去掉 markdown 表格的表头行：'a | b' 后紧跟 '--- | ---' 时，两者都丢。

    注意：必须在 clean() 把 | 转成 ' / ' 之前调用，否则 is_table_row() 永远为假。
    """
    out = []
    skip_next = False
    for i, s in enumerate(items):
        if skip_next:
            skip_next = False
            continue
        nxt = items[i + 1] if i + 1 < len(items) else ""
        if is_table_row(s) and is_table_noise(nxt):
            skip_next = True
            continue
        if is_table_noise(s):
            continue
        out.append(s)
    return out


def is_boilerplate(s):
    """说明性废话，不含决策信息。仅匹配行首，避免误伤正文。"""
    prefixes = ("本场新增", "本场复检", "与基线对比", "命令：", "执行时间",
                "上一份", "复检范围", "上一场", "DeepInfra 是本场",
                "stars 变动明细", "新增额度项", "唯一观察项", "原因：",
                "判定：", "跟进：")
    return s.startswith(prefixes)


def is_command_echo(s):
    """verify.py 的命令回显行。"""
    return s.startswith(("$", "python3 ", "cd ", "> "))


def drop_unchanged(items):
    """额度变化里，'无变化' 的行整条丢弃——推送只讲变化。"""
    kept = []
    for s in items:
        if "无变化" in s and "★" not in s:
            continue
        kept.append(s)
    # 概览行（如 'new-api stars / 50,554 / 50,556 / +2'）与明细行重复
    kept = [x for x in kept if not re.match(r"^[\w\-./]+ stars / \d", x)]
    # stars 明细中数字未变的（'a → a ( 0,'）也没有信息量
    kept = [x for x in kept if not re.match(r"^\S+ \d[\d,]* → \d[\d,]* \( 0,", x)]
    # 本场新条目（'xxx 新条目 N'）已在【新增】列出，此处不重复
    kept = [x for x in kept if "新条目" not in x]
    return kept


def clean(lines):
    """去空行、去 markdown 语法噪音，保留有效内容行。

    表头剥离在原始行（仍含 |）上按索引做，因为后续会把 | 转成 ' / '。
    """
    # 第一遍：过滤掉空行/分隔行/命令回传，并标记表头行
    keep = []          # (原始行文本, 是否表头)
    in_code = False
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if is_table_sep(s):
            # 分隔行：其上紧邻的一行就是表头，标记后丢弃分隔行自身
            if keep and is_table_row(keep[-1][0]):
                keep[-1] = (keep[-1][0], True)
            continue
        if not s or s in ("---", "***"):
            continue
        if in_code:
            if is_command_echo(s):
                continue
        elif is_command_echo(s):
            continue
        keep.append((s, False))

    pairs = []
    for s, is_header in keep:
        if is_header:
            continue
        t = re.sub(r"^[-*+]\s+", "", s)                 # 列表符号
        t = re.sub(r"^#+\s*", "", t)                    # 残留标题符号
        t = re.sub(r"^\|+|\|+$", "", t)                 # 表格行首尾管道符
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)          # 加粗
        t = re.sub(r"`([^`]+)`", r"\1", t)              # 行内代码
        t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)      # 图片
        t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)  # 链接保留文字
        t = re.sub(r"\s*\|\s*", " / ", t)               # 表格单元格分隔
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        if t in ("无", "无。", "无新增", "无变化"):
            t = "无"
        pairs.append(t)
    return [t for t in pairs if not is_boilerplate(t)]


def summarize_verify(items):
    """复检结果：把逐行 ok/unverified 压成一行统计，异常才列明细。

    只认「条目行」——形如 '<status> <id> <- ...' 的 verify.py 输出。
    说明文字（如 '11/11 通过'、'唯一观察项：…'）不计入统计，否则会误判为异常。
    """
    ok = bad = 0
    details = []
    for it in items:
        m = re.match(r"^(ok|expired|unverified|dead|fail|skip)\s+(\S+)", it)
        if not m:
            continue
        status, entry_id = m.group(1), m.group(2)
        if status == "ok":
            ok += 1
            continue
        bad += 1
        details.append(f"{entry_id}: {it.split('<-', 1)[-1].strip()[:60]}")
    if ok == 0 and bad == 0:
        return ["无"]
    summary = f"{ok} 项通过"
    if bad:
        summary += f"，{bad} 项异常 — " + "；".join(details[:3])
    return [summary]


def truncate(text):
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    idx = cut.rfind("\n")
    return cut[:idx if idx > MAX_CHARS * 0.6 else MAX_CHARS].rstrip() + "\n…（已截断，完整版见仓库）"


SECTION_LIMIT = {"新增": 5, "失效清单": 3, "额度变化": 4, "复检结果": 3}


def build_text(sections, source):
    parts = []
    for name in SECTIONS:
        items = clean(sections.get(name, []))
        if name == "复检结果":
            items = summarize_verify(items)
        elif name == "额度变化":
            items = drop_unchanged(items)
        if not items:
            items = ["无"]
        # 失效清单用极简表达：'无失效。' 而非整句解释
        if name == "失效清单" and len(items) == 1 and items[0] != "无":
            items = ["无失效"]
        limit = SECTION_LIMIT.get(name, 5)
        body = "\n".join(f"• {i}" if i != "无" else "• 无" for i in items[:limit])
        parts.append(f"【{name}】\n{body}")
    head = extract_title(source)
    return truncate(head + "\n\n" + "\n\n".join(parts))


def build_json(sections, source):
    data = {"title": extract_title(source),
            "source": source, "sections": {}}
    for name in SECTIONS:
        items = clean(sections.get(name, []))
        if name == "复检结果":
            items = summarize_verify(items)
        data["sections"][name] = items[:8] if items else ["无"]
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供推送脚本消费")
    args = ap.parse_args()

    if not os.path.exists(args.snapshot):
        print(f"not found: {args.snapshot}", file=sys.stderr)
        return 1

    sections = parse_snapshot(args.snapshot)
    # 护栏：只有「预期小节」（SECTIONS 里的节名本身作为标题）真的命中时才继续。
    # parse_snapshot 的键是标题全文，'## 本期新增（…）' 这种标题会存入字典却
    # 不会被 build_text 读取，最终只剩一行标题加四个「无」——静默残骸比报错更糟。
    hits = [name for name in SECTIONS if name in sections]
    if not hits:
        print(f"error: {args.snapshot} 未匹配到任何预期小节", file=sys.stderr)
        print(f"期望的节名（SECTIONS）：{' / '.join(SECTIONS)}", file=sys.stderr)
        print("本脚本只适用于任务 1 快照；任务 2/3 请手写摘要推送。", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(build_json(sections, args.snapshot), ensure_ascii=False, indent=2))
    else:
        print(build_text(sections, args.snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
