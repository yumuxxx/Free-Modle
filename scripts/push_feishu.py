#!/usr/bin/env python3
"""通过飞书开放平台 API 主动推送文本消息给 owner。

凭证来源（按优先级）：
  1. 环境变量 FEISHU_APP_SECRET
  2. /root/.dsh/.credentials.yaml 中 refs.DSH_FEISHU_APP_SECRET_<hex>
     —— 即 dsh-feishu 插件激活时写入的 app secret，与已运行的 "Free Model" 机器人同源。

appId / ownerOpenId 从 /root/.dsh/integrations/dsh-feishu/config.json 读取，
避免硬编码。文件不存在时回退到内置默认值。

用法：
  python3 scripts/push_feishu.py --text "消息内容"
  python3 scripts/push_feishu.py --file data/snapshots/2026-10-23-evening.md   # 先提纯再推送
  python3 scripts/push_feishu.py --text "..." --dry-run                        # 只打印不发送

退出码：0 成功；1 参数/文件错误；2 凭证缺失；3 发送失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

CRED_FILE = "/root/.dsh/.credentials.yaml"
PLUGIN_CFG = "/root/.dsh/integrations/dsh-feishu/config.json"
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

DEFAULT_APP_ID = "cli_aa50f6fbeeb8dc0b"
DEFAULT_OWNER = "ou_7d06e9ec3f9361f77cd9d774b616d140"
TIMEOUT = 20


# ---------- 凭证 ----------

def load_secret() -> str:
    """读取 app secret：环境变量优先，其次 dsh 凭证库。"""
    v = os.environ.get("FEISHU_APP_SECRET")
    if v:
        return v.strip()
    try:
        s = open(CRED_FILE, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"[push_feishu] 无法读取 {CRED_FILE}: {e}")
    m = re.search(r"DSH_FEISHU_APP_SECRET_[0-9A-Fa-f]+:\s*(\S+)", s)
    if not m:
        sys.exit(f"[push_feishu] {CRED_FILE} 中未找到 DSH_FEISHU_APP_SECRET_* 引用")
    return m.group(1).strip()


def load_cfg() -> tuple[str, str]:
    """读取 (app_id, owner_open_id)。插件配置优先，回退默认值。"""
    app_id, owner = DEFAULT_APP_ID, DEFAULT_OWNER
    try:
        cfg = json.load(open(PLUGIN_CFG, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return app_id, owner
    for bot in cfg.get("bots", []):
        if bot.get("activated") == 2:
            app_id = bot.get("appId") or app_id
            break
    ids = cfg.get("ownerOpenIds") or []
    if ids:
        owner = ids[0]
    return app_id, owner


# ---------- HTTP ----------

def _post(url: str, payload: dict, headers: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_token(app_id: str, secret: str) -> str:
    d = _post(TOKEN_URL, {"app_id": app_id, "app_secret": secret})
    if d.get("code") != 0:
        sys.exit(f"[push_feishu] 获取 tenant_access_token 失败: code={d.get('code')} msg={d.get('msg')}")
    return d["tenant_access_token"]


def send(token: str, app_id: str, owner: str, text: str) -> str:
    payload = {
        "receive_id": owner,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    req = urllib.request.Request(
        f"{SEND_URL}?receive_id_type=open_id",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"[push_feishu] HTTP {e.code}: {detail}")
    if d.get("code") != 0:
        sys.exit(f"[push_feishu] 发送失败: code={d.get('code')} msg={d.get('msg')}")
    return d.get("data", {}).get("message_id", "")


# ---------- 入口 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="飞书消息推送（Free Model 调研摘要）")
    ap.add_argument("--text", help="直接推送的文本内容")
    ap.add_argument("--file", help="快照 markdown 路径，先提纯为摘要再推送")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = ap.parse_args()

    if not args.text and not args.file:
        ap.error("必须提供 --text 或 --file 之一")

    text = args.text
    if args.file:
        if not os.path.isfile(args.file):
            sys.exit(f"[push_feishu] 文件不存在: {args.file}")
        # 复用 distill.py 的提纯逻辑，保证推送内容与仓库摘要一致
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        import distill
        sections = distill.parse_snapshot(args.file)
        text = distill.build_text(sections, args.file)

    if not text or not text.strip():
        sys.exit("[push_feishu] 内容为空，未发送")

    if args.dry_run:
        print(text)
        return 0

    secret = load_secret()
    app_id, owner = load_cfg()
    token = get_token(app_id, secret)
    mid = send(token, app_id, owner, text)
    print(f"[push_feishu] 已推送 message_id={mid} ({len(text)} 字符)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
