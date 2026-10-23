#!/usr/bin/env python3
"""通过钉钉开放平台 API 主动推送消息。

凭证来源（按优先级）：
  1. 环境变量 DINGTALK_APP_KEY / DINGTALK_APP_SECRET / DINGTALK_ROBOT_CODE
  2. /root/.dsh/.credentials.yaml 的 refs.DSH_DINGTALK_BOT_SECRET_<hex>
     + /root/.dsh/integrations/dsh-dingtalk/config.json 的 clientId

接收人默认取 /root/.dsh/integrations/dsh-dingtalk/bots/*/state.json 中
已知的 p2p 会话用户 id（即与机器人私聊过的人），也可用 --user 覆盖。

用法：
  python3 scripts/push_dingtalk.py --text "消息内容"
  python3 scripts/push_dingtalk.py --file <snapshot.md>     # 先提纯再推送
  python3 scripts/push_dingtalk.py --title "标题" --file x.md  # markdown 消息
  python3 scripts/push_dingtalk.py --text "..." --dry-run

退出码：0 成功；1 参数/文件错误；2 凭证缺失；3 发送失败。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

CRED_FILE = "/root/.dsh/.credentials.yaml"
PLUGIN_DIR = "/root/.dsh/integrations/dsh-dingtalk"
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
TIMEOUT = 20


# ---------- 凭证与接收人 ----------

def load_cred() -> tuple[str, str, str]:
    """返回 (app_key, app_secret, robot_code)。"""
    app_key = os.environ.get("DINGTALK_APP_KEY")
    secret = os.environ.get("DINGTALK_APP_SECRET")
    robot_code = os.environ.get("DINGTALK_ROBOT_CODE")

    if not secret:
        try:
            s = open(CRED_FILE, encoding="utf-8").read()
        except OSError as e:
            sys.exit(f"[push_dingtalk] 无法读取 {CRED_FILE}: {e}")
        m = re.search(r"DSH_DINGTALK_BOT_SECRET_[0-9A-Fa-f]+:\s*(\S+)", s)
        if not m:
            sys.exit("[push_dingtalk] 凭证库中未找到 DSH_DINGTALK_BOT_SECRET_*")
        secret = m.group(1).strip()

    if not app_key or not robot_code:
        try:
            cfg = json.load(open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8"))
            for bot in cfg.get("bots", []):
                app_key = app_key or bot.get("clientId")
                robot_code = robot_code or bot.get("clientId")
        except (OSError, json.JSONDecodeError):
            pass

    if not app_key:
        sys.exit("[push_dingtalk] 未找到 app_key（clientId）")
    # 钉钉机器人 robotCode 与 clientId 通常一致
    return app_key, secret, robot_code or app_key


def load_user() -> str:
    """从 bot state.json 取最近一个 p2p 会话用户 id。"""
    env_uid = os.environ.get("DINGTALK_USER_ID")
    if env_uid:
        return env_uid
    for state_path in glob.glob(os.path.join(PLUGIN_DIR, "bots", "*", "state.json")):
        try:
            st = json.load(open(state_path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in st.get("sessions", {}):
            if key.startswith("p2p:"):
                return key.split(":", 1)[1]
    sys.exit("[push_dingtalk] 未找到接收人：请先用钉钉与机器人私聊一句，或用 --user 指定")


# ---------- HTTP ----------

def _post(url: str, payload: dict, headers: dict) -> dict | str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        sys.exit(f"[push_dingtalk] HTTP {e.code}: {detail}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def get_token(app_key: str, secret: str) -> str:
    d = _post(TOKEN_URL, {"appKey": app_key, "appSecret": secret}, {})
    if not isinstance(d, dict) or not d.get("accessToken"):
        sys.exit(f"[push_dingtalk] 获取 accessToken 失败: {d}")
    return d["accessToken"]


def send(token: str, robot_code: str, user: str, text: str, title: str | None = None) -> None:
    if title:
        # markdown 消息，支持简单排版
        msg_key = "sampleMarkdown"
        msg_param = {"title": title, "text": text}
    else:
        msg_key = "sampleText"
        msg_param = {"content": text}
    payload = {
        "robotCode": robot_code,
        "userIds": [user],
        "msgKey": msg_key,
        "msgParam": json.dumps(msg_param, ensure_ascii=False),
    }
    d = _post(SEND_URL, payload, {"x-acs-dingtalk-access-token": token})
    if isinstance(d, dict):
        if d.get("invalidStaffIdList"):
            sys.exit(f"[push_dingtalk] 接收人无效: {d['invalidStaffIdList']}")
        if d.get("filteredStaffIdList"):
            sys.exit(f"[push_dingtalk] 消息被过滤（可能不在机器人可见范围）: {d['filteredStaffIdList']}")
    print(f"[push_dingtalk] 已推送 ({len(text)} 字符) -> {user}")


# ---------- 入口 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="钉钉消息推送")
    ap.add_argument("--text", help="直接推送的文本内容")
    ap.add_argument("--file", help="markdown 文件路径，先提纯为摘要再推送")
    ap.add_argument("--title", help="markdown 消息标题（提供则按 markdown 发送）")
    ap.add_argument("--user", help="接收人 staffId，默认取 state.json 中最近会话用户")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = ap.parse_args()

    if not args.text and not args.file:
        ap.error("必须提供 --text 或 --file 之一")

    text = args.text
    if args.file:
        if not os.path.isfile(args.file):
            sys.exit(f"[push_dingtalk] 文件不存在: {args.file}")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import distill
        sections = distill.parse_snapshot(args.file)
        text = distill.build_text(sections, args.file)

    if not text or not text.strip():
        sys.exit("[push_dingtalk] 内容为空，未发送")

    if args.dry_run:
        print(text)
        return 0

    app_key, secret, robot_code = load_cred()
    user = args.user or load_user()
    token = get_token(app_key, secret)
    send(token, robot_code, user, text, args.title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
