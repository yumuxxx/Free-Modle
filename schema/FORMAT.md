# 字段含义与写入规则

## 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 查重主键。小写，`/` 分隔，通常 `provider/model_family`。例：`openrouter/llama-3.3-70b`、`google/gemini-2.0-flash`、`github-pool/one-api` |
| `name` | 是 | 展示名 |
| `category` | 是 | `aggregator`（聚合平台）/ `vendor-api`（厂商官方）/ `open-source`（开源项目） |
| `provider` | 是 | 提供方名称 |
| `model_family` | 否 | 模型系列 |
| `status` | 是 | `active` / `expired` / `unverified` / `superseded` |
| `free_tier` | 否 | 免费额度文字描述 |
| `quota_checked_at` | 否 | 额度核对时间，**只要写了额度数字就必须填** |
| `endpoint` | 否 | API 端点，复检用 |
| `signup_url` | 否 | 注册地址，复检用 |
| `source_url` | 是 | 信息来源 |
| `first_seen` | 是 | 首次记录时间 |
| `last_seen` | 是 | 最近确认存在时间 |
| `verify_fail_count` | 否 | 连续复检失败次数 |
| `expired_reason` | 否 | 失效原因 |
| `notes` | 否 | 限制条件、风控等 |

## 写入规则

1. 每条记录是 `data/index.jsonl` 里的一行 JSON，字段顺序固定，便于 diff。
2. 新条目写入前先跑 `scripts/dedupe.py`，若 `id` 已存在：
   - 原条目 `status=active` → 只更新 `last_seen` 与 `quota_checked_at`，不新增行。
   - 原条目 `status=expired` → 视为"复活"，改写该行并清零 `verify_fail_count`。
3. 时间一律 ISO 8601 带 `+08:00` 偏移（Asia/Shanghai）。
4. `free_tier` 是文字描述而非结构化数字，因为各家单位不同（requests/day、tokens/min、credits）。
5. 快照报告命名：`data/snapshots/YYYY-MM-DD-noon.md`（12:00 场）与 `YYYY-MM-DD-evening.md`（18:00 场）。
6. 每次快照必须包含三节：**新增**、**失效清单**、**额度变化**。无内容时写"无"。
7. 失效判定优先级：官方公告 > 接口返回 401/402/404/410 > 连续 2 次复检失败 > GitHub 仓库 archived。

## 复检（verify.py）行为

- 对每个 `status=active` 的条目，优先探测 `endpoint`，失败则探测 `signup_url`。
- 探测视为成功的条件：HTTP 2xx/3xx，或 401/403（说明服务存在、只是要鉴权）。
- 404/410/GitHub archived → 直接置 `expired`。
- 其他失败（超时、5xx、DNS）→ `verify_fail_count += 1`；达到 2 置 `expired`，否则保持 `unverified`。
- 成功 → `verify_fail_count = 0`，`last_seen` 更新为当前时间。
