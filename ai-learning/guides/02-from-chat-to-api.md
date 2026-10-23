# 02 · 从对话到 API

> 目标：让 AI 从"聊天窗口里的帮手"变成"脚本里的一个函数"。
> 前置：能写基础提示词（`references/01`），懂一点命令行。
> 预计时间：1 周（含跑通第一个脚本）。

---

## 什么时候需要 API

先判断你是否真的需要：

| 情况 | 用对话 | 用 API |
|------|--------|--------|
| 一次性问题 | ✅ | ❌ |
| 每天重复同一个任务 | ❌ | ✅ |
| 需要处理 100 个文件 | ❌ | ✅ |
| 结果要进数据库 / 发通知 | ❌ | ✅ |
| 半夜自动跑 | ❌ | ✅ |

**判断标准：这件事你会做第二次吗？** 会，就值得写成脚本。

---

## 核心概念（5 分钟）

API 调用本质就是**用代码发一次对话请求**。

```
你在网页里：打字 → 点发送 → 等回复 → 复制结果
用 API：    构造请求 → POST 到接口 → 解析 JSON → 拿到文本
```

需要知道的四个概念：

| 概念 | 说明 |
|------|------|
| **API Key** | 你的身份凭证，相当于密码。**绝不能写进代码提交到公开仓库** |
| **Endpoint** | 请求发往的网址，如 `https://api.example.com/v1/chat/completions` |
| **Token** | 计费单位，大致 1 个汉字 ≈ 1–2 token。输入输出都计费 |
| **上下文窗口** | 单次请求能携带的最大 token 数，超了要截断或分段 |

---

## 第一步：跑通最小请求（1 小时）

### 用 curl

```bash
curl https://api.example.com/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "model-name",
    "messages": [
      {"role": "user", "content": "用一句话解释什么是递归"}
    ]
  }'
```

返回是一坨 JSON，你要的内容在 `choices[0].message.content`。

### 用 Python

```python
import json
import os
import urllib.request

API_KEY = os.environ["API_KEY"]          # 从环境变量读，不写死在代码里

payload = {
    "model": "model-name",
    "messages": [{"role": "user", "content": "用一句话解释什么是递归"}],
}

req = urllib.request.Request(
    "https://api.example.com/v1/chat/completions",
    data=json.dumps(payload).encode(),
    method="POST",
)
req.add_header("Authorization", f"Bearer {API_KEY}")
req.add_header("Content-Type", "application/json")

with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

print(data["choices"][0]["message"]["content"])
```

**这一步的目标不是理解每一行，是让它在你的机器上成功跑出结果。**

---

## 第二步：理解 messages 数组（1 小时）

对话是有角色的，API 里体现为 messages 数组：

```python
messages = [
    {"role": "system", "content": "你是一位严谨的技术文档编辑，只修正事实错误，不改写风格"},
    {"role": "user", "content": "第一版内容"},
    {"role": "assistant", "content": "（上一轮 AI 的回复）"},
    {"role": "user", "content": "第二段还是太啰嗦"},
]
```

| role | 作用 |
|------|------|
| `system` | 设定全局行为，相当于提示词里的"角色 + 约束" |
| `user` | 你的输入 |
| `assistant` | AI 的历史回复（多轮对话要带上） |

**关键点**：API **默认无记忆**。每一轮都要把完整历史放进 messages，否则它不记得上文。这就是为什么长对话的 API 调用会很贵。

---

## 第三步：处理真实世界的麻烦（2–3 天）

### 3.1 限流与重试

免费额度一定有速率限制。收到 `429` 时：

```python
import time

for attempt in range(5):
    try:
        return call_api(...)
    except RateLimitError:
        time.sleep(2 ** attempt)     # 指数退避：2s, 4s, 8s, 16s...
raise RuntimeError("重试 5 次仍失败")
```

**不要用固定 sleep**。指数退避是标准做法。

### 3.2 超时

永远设超时，否则一个卡住的请求能挂你一小时：

```python
with urllib.request.urlopen(req, timeout=30) as resp:
```

### 3.3 输出不可控

让 AI 返回 JSON，它可能给你 ````json ... ``` `包着，或多一段解释。处理办法：

- **提示词层面**：明确说"只输出 JSON，不要任何解释"
- **代码层面**：写一个提取函数，从回复中抠出第一个 `{` 到最后一个 `}` 之间的内容
- **架构层面**：解析失败就重试，3 次后放弃并记录原文

### 3.4 成本失控

最容易犯的错：**在循环里调用 API，忘记录用量**。

```python
total_tokens = 0
for item in items:
    result = call_api(item)
    total_tokens += result["usage"]["total_tokens"]
    print(f"已用 {total_tokens} tokens")
```

先小批量跑 10 条，看单条平均用量，再估算全量成本。

---

## 第四步：把脚本变成自动化（1–2 天）

到这一步，你已经有"能跑的脚本"。要它每天自己跑：

### 用系统定时任务

```bash
crontab -e
# 每天 18:00 执行，日志追加到文件
0 18 * * * cd /path/to/project && /usr/bin/python3 script.py >> run.log 2>&1
```

**三条必知**：
1. **cron 的环境比你的终端干净得多** —— 你在终端里能用的命令、环境变量、代理设置，cron 里可能都没有。脚本里要用绝对路径
2. **先手动跑通，再挂 cron** —— 没跑通过的脚本挂上 cron，你只会看到一堆没输出的日志
3. **日志必须落盘** —— cron 不弹窗，出错你只能靠日志查

### 把密钥放到环境变量

```bash
# ~/.bashrc 或 systemd unit 里
export API_KEY="sk-..."
```

代码里 `os.environ["API_KEY"]`。**这样代码可以安全提交到公开仓库。**

---

## 安全红线

- [ ] **绝不**把 API Key 写进代码文件
- [ ] **绝不**提交 `.env` 或含密钥的配置文件（加进 `.gitignore`）
- [ ] **绝不**把密钥贴到对话窗口、Issue、截图里
- [ ] 密钥泄露后**立刻去后台轮换**，不要只是"改一下"
- [ ] 给密钥设用量上限和告警

---

## 学习路径总结

```
跑通最小请求 → 理解 messages → 处理限流/超时/解析 → 挂上定时任务
    1h            1h              2-3 天              1-2 天
```

跑完这条线，你就能做出"每天自动帮我做某事并推送到我手机上"的东西——比如本仓库的其他自动化任务。

---

*记录日期：2026-10-23 · 接口细节以各服务商官方文档为准*
