# Free-Modle

免费 AI 资源与学习资料库。每天 **18:00**（Asia/Shanghai）由三个定时任务自动更新，内容同时推送钉钉（机器人别名 **Free Model**）。

- 仓库地址：<https://github.com/yumuxxx/Free-Modle>
- 维护方式：全自动（DSH 定时任务），无需人工干预
- 推送通道：钉钉（`scripts/push_dingtalk.py`）+ 飞书（`scripts/push_feishu.py`）

> [!warning] 写入规范（定时任务与人工维护都必须遵守）
> 1. **新建文件与目录名一律英文 kebab-case**，中文只做正文说明。
>    正确示例：`01-prompt-engineering-basics.md`；反例见本次改名记录（全部改为英文语义名）。
>    （历史上曾产出 7 个中文路径文件，已全部改名，不得再产生。）
> 2. **产出中禁止写任何本地绝对路径**（`/root/...`、`/home/...`、`/mnt/...`）。
>    需要指代凭据文件时写占位符：`<GITHUB-PAT-FILE>`、`<WEBHOOK-FILE>`。
>    （历史上曾把绝对路径写进快照并推到 PUBLIC 仓库，属红线，不得再犯。）
> 3. 涉及凭据只写「从凭证机制自动读取」，不写文件名、不写内容。

---

## 三个板块

| 板块 | 回答什么问题 | 目录 |
|------|-------------|------|
| **免费用什么** | 哪里有免费额度、哪个还活着 | [`data/`](data/) |
| **怎么用 AI** | 从零开始学，循序渐进 | [`ai-learning/`](ai-learning/) |
| **用什么方案** | GitHub 上反响好的项目排行 | [`github-trending/`](github-trending/) |

---

## 定时任务

| 任务 | 时间 | 产出 |
|------|------|------|
| 免费模型调研 | 每天 18:00 | `data/snapshots/YYYY-MM-DD-evening.md` + `data/index.jsonl` 更新 |
| AI 学习资料收集 | 每天 18:00 | `ai-learning/weekly/YYYY-MM-DD-weekly.md` + 新资料 |
| GitHub AI 方案排行 | 每天 18:00 | `github-trending/daily/YYYY-MM-DD.md`（两份榜单） |

三个任务各自独立跑，互不依赖；任一个失败不影响其他任务。

---

## 目录结构

```
Free-Modle/
  data/
    index.jsonl            # 全量条目索引（每条一行，机器可读，查重主依据）
    snapshots/             # 免费额度调研快照（按日期命名）
  ai-learning/
    README.md              # 学习路线图 L0→L4，从这里开始
    guides/                # 方法论：提示词工作流、从对话到 API
    tutorials/             # 实操教程：含必修练习
    references/            # 速查：提示词入门、模型对比、术语表
    weekly/                # 每周精选与学习建议
  github-trending/
    README.md              # 榜单口径说明
    daily/                 # 每日受欢迎排行 + 新品排行
    weekly/                # 每周汇总
    monthly/               # 每月沉淀
    projects/              # 重点项目档案（持续跟踪 star）
  schema/
    entry.schema.json      # 单条目字段定义
    FORMAT.md              # 字段含义与写入规则
  scripts/
    dedupe.py              # 查重：比对 index.jsonl 与新条目
    verify.py              # 复检：重新验证条目可用性，标记 expired
    distill.py             # 提纯：把快照压缩成 ≤900 字符摘要
    push_feishu.py         # 飞书推送（开放平台 API）
    push_dingtalk.py       # 钉钉推送（开放平台 API）
```

---

## 推送机制

两个推送脚本都不需要 webhook，直接走开放平台 API：

- **飞书**：`tenant_access_token` → `POST /open-apis/im/v1/messages?receive_id_type=open_id`
- **钉钉**：`accessToken` → `POST /v1.0/robot/oToMessages/batchSend`

凭证来源：
- 飞书 app secret —— `/root/.dsh/.credentials.yaml` 的 `refs.DSH_FEISHU_APP_SECRET_*`
- 钉钉 app secret —— 同文件的 `refs.DSH_DINGTALK_BOT_SECRET_*`
- appId / clientId / 接收人 open_id —— 对应插件 `config.json`

**凭证不进仓库**（`.gitignore` 已排除 `.secrets/`）。

---

## 条目状态（data/ 板块）

| 状态 | 含义 |
|------|------|
| `active` | 最近一次复检可用，可正常使用 |
| `expired` | 已确认失效（需注册/额度取消/项目停更/接口 404/410 等） |
| `unverified` | 尚未复检或复检结果不确定 |
| `superseded` | 被同一来源的更新版本替代，保留仅为历史记录 |

---

## 查重与排障规则

1. **查重主键**：`id`（小写化后的规范键，通常为 `provider + model_family`）。同一 `id` 只保留最新一条，旧条目转入历史。
2. **失效判定**：`verify.py` 会对 `endpoint` 或 `signup_url` 发探测请求；连续 2 次复检失败即置 `expired`，并在快照报告中列入"失效清单"。
3. **不重复记录**：已在 `index.jsonl` 且状态为 `active` 的条目，只更新 `last_seen`，不新增条目。
4. 免费额度数字一律附 `checked_at`，注明"截至何时"，避免过期数字被当成现值。
5. 端点返回 **401/403 视为存活**（服务存在、需鉴权），不算失败；**404/410 才算失效**。

---

## 免责声明

本仓库仅记录公开可查的免费额度信息与开源项目情况，实际额度、限制与可用性以各服务商当期官方说明为准。记录不等于推荐，使用前请自行确认服务条款。
