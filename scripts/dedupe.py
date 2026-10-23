#!/usr/bin/env python3
"""查重：比对 index.jsonl 与待写入的新条目。

用法：
    python3 scripts/dedupe.py data/index.jsonl new_entries.jsonl

输出（stdout，JSON）：
    {"new": [...], "update": [...], "revive": [...]}

- new    : id 不存在，需新增
- update : id 已存在且原状态 active，只更新 last_seen/quota_checked_at
- revive : id 已存在但原状态 expired，需改写该行
"""
import json
import sys


def load_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    index_path, new_path = sys.argv[1], sys.argv[2]
    existing = {row["id"]: row for row in load_jsonl(index_path)}
    candidates = load_jsonl(new_path)

    out = {"new": [], "update": [], "revive": []}
    for cand in candidates:
        cid = cand["id"]
        if cid not in existing:
            out["new"].append(cand)
        elif existing[cid].get("status") == "expired":
            out["revive"].append(cand)
        else:
            out["update"].append(cand)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
