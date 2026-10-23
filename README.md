# Free-Modle

免费 LLM / API 调研库。每天 **12:00** 与 **18:00**（Asia/Shanghai）各自动检索一次，把结果写进本仓库，用于后续查重与排除失效方案。

- 仓库地址：<https://github.com/yumuxxx/Free-Modle>
- 维护方式：全自动（DSH 定时任务），无需人工干预
- 检索范围：聚合平台免费额度 / 各厂商官方免费 API / 开源免费代理与池化项目

## 目录结构

```
data/
  index.jsonl          # 全量条目索引（每条一行，机器可读，查重主依据）
  snapshots/           # 每次检索的快照报告（按日期+时段命名）
schema/
  entry.schema.json    # 单条目字段定义
  FORMAT.md            # 字段含义与写入规则
scripts/
  dedupe.py            # 查重：比对 index.jsonl 与新条目
  verify.py            # 复检：重新验证条目可用性，标记 expired
README.md
```

## 条目状态

| 状态 | 含义 |
|------|------|
| `active` | 最近一次复检可用，可正常使用 |
| `expired` | 已确认失效（需注册/额度取消/项目停更/接口 404/410 等） |
| `unverified` | 尚未复检或复检结果不确定 |
| `superseded` | 被同一来源的更新版本替代，保留仅为历史记录 |

## 查重与排障规则

1. **查重主键**：`id`（小写化后的规范键，通常为 `provider + model_family`）。同一 `id` 只保留最新一条，旧条目转入历史。
2. **失效判定**：`verify.py` 会对 `endpoint` 或 `signup_url` 发探测请求；连续 2 次复检失败即置 `expired`，并在快照报告中列入"本期失效清单"。
3. **不重复记录**：已在 `index.jsonl` 且状态为 `active` 的条目，只更新 `last_seen`，不新增条目。
4. 免费额度数字一律附 `checked_at`，注明"截至何时"，避免过期数字被当成现值。

## 报告怎么看

- `data/index.jsonl` —— 当前有效的全部条目，一行一个，适合 grep / 程序处理。
- `data/snapshots/YYYY-MM-DD-noon.md` / `-evening.md` —— 当天中午/下午的检索报告，含新增、失效、变化三项。
- 失效方案集中在快照报告的"失效清单"小节，便于快速排除。

## 免责声明

本仓库仅记录公开可查的免费额度信息，实际额度、限制与可用性以各服务商当期官方说明为准。记录不等于推荐，使用前请自行确认服务条款。
