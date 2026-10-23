#!/usr/bin/env python3
"""复检：重新验证条目可用性，标记 expired。

用法：
    python3 scripts/verify.py [data/index.jsonl] [--timeout 12] [--dry-run]

行为（见 schema/FORMAT.md「复检（verify.py）行为」）：
  - 优先探测 endpoint，失败再探测 signup_url
  - 2xx/3xx 或 401/403 视为成功（服务存在，只是要鉴权）
  - 404/410 直接置 expired
  - 超时 / 5xx / DNS 失败累计 verify_fail_count，达到 2 置 expired
  - 成功后 verify_fail_count 归零，last_seen 更新

默认 --dry-run，只打印计划变更，不写文件。加 --write 才会落盘。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
OK_CODES = {200, 201, 202, 204, 301, 302, 303, 307, 308, 401, 403}
DEAD_CODES = {404, 410}


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def probe(url, timeout):
    """返回 (result, detail)。result ∈ ok|dead|fail"""
    if not url:
        return "fail", "no url"
    if url.startswith("github:"):
        repo = url[len("github:"):]
        return probe_github_repo(repo, timeout)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; Free-Modle-verify/1.0)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return "ok", f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in DEAD_CODES:
            return "dead", f"HTTP {exc.code}"
        if exc.code in OK_CODES:
            return "ok", f"HTTP {exc.code}"
        return "fail", f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - 探测失败不区分类型
        return "fail", f"{type(exc).__name__}: {exc}"


def probe_github_repo(repo, timeout):
    """github:owner/name -> ok|dead|fail。404/410 或 archived 视为 dead。"""
    url = f"https://api.github.com/repos/{repo}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Free-Modle-verify/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in DEAD_CODES:
            return "dead", f"HTTP {exc.code}"
        if exc.code in OK_CODES:
            return "ok", f"HTTP {exc.code}"
        return "fail", f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return "fail", f"{type(exc).__name__}: {exc}"

    if data.get("archived"):
        return "dead", "repo archived"
    pushed = data.get("pushed_at", "")
    return "ok", f"repo active (pushed {pushed[:10]}, stars {data.get('stargazers_count')})"


def run_probe(url, timeout):
    """带硬超时执行探测，规避 proxychains 环境下 urllib 超时不准的问题。"""
    code = (
        "import sys, json\n"
        "from verify import probe\n"
        "url, timeout = sys.argv[1], float(sys.argv[2])\n"
        "res, detail = probe(url, timeout)\n"
        "print(json.dumps([res, detail]))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, url, str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 8,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    except subprocess.TimeoutExpired:
        return "fail", "hard timeout"
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return "fail", (proc.stderr or "no output").strip()[-160:]
    try:
        res, detail = json.loads(out[-1])
        return res, detail
    except Exception:  # noqa: BLE001
        return "fail", out[-1][-160:]


def check_entry(entry, timeout):
    last = "no url to probe"
    for key in ("endpoint", "signup_url"):
        if entry.get(key):
            result, detail = run_probe(entry[key], timeout)
            last = f"{key} {detail}"
            if result == "ok":
                return "ok", last
            if result == "dead":
                return "dead", last
    return "fail", last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("index", nargs="?", default="data/index.jsonl")
    ap.add_argument("--timeout", type=int, default=12, help="单次探测超时（秒）")
    ap.add_argument("--budget", type=int, default=180, help="整轮复检总预算（秒），超时即停止")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run）")
    args = ap.parse_args()

    try:
        with open(args.index, encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        print(f"index not found: {args.index}", file=sys.stderr)
        return 1

    started = time.monotonic()
    changed = []
    skipped = 0
    for entry in entries:
        if entry.get("status") != "active":
            continue
        if time.monotonic() - started > args.budget:
            skipped += 1
            continue
        result, detail = check_entry(entry, args.timeout)
        eid = entry["id"]
        if result == "ok":
            entry["verify_fail_count"] = 0
            entry["last_seen"] = now_iso()
            changed.append((eid, "ok", detail))
        elif result == "dead":
            entry["status"] = "expired"
            entry["expired_reason"] = f"verify: {detail}"
            changed.append((eid, "expired", detail))
        else:
            entry["verify_fail_count"] = entry.get("verify_fail_count", 0) + 1
            if entry["verify_fail_count"] >= 2:
                entry["status"] = "expired"
                entry["expired_reason"] = f"verify: 2 consecutive failures, last={detail}"
                changed.append((eid, "expired", detail))
            else:
                entry["status"] = "unverified"
                changed.append((eid, "unverified", f"{detail} (fail {entry['verify_fail_count']})"))

    for eid, status, detail in changed:
        print(f"{status:10s} {eid}  <- {detail}")
    if skipped:
        print(f"skipped   {skipped} entries (budget {args.budget}s exceeded)")

    if args.write:
        with open(args.index, "w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.index} ({len(entries)} entries, {len(changed)} changed)")
    else:
        print(f"\ndry-run: {len(changed)} would change (pass --write to apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
