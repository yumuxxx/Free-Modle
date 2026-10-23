# MCP 入门：让 AI 连上你的工具

> 本篇属 **L4 进阶**：你已经会写提示词、会调 API 之后，再来看这个。
> 资料来源：Model Context Protocol 官方文档（2026-07-28 版）
> 官方原文：<https://modelcontextprotocol.io/docs/getting-started/intro>
> 整理日期：2026-10-24

---

## 一句话理解

**MCP 是 AI 应用的 USB-C 接口。**

USB-C 让手机、硬盘、显示器用同一个口互联，MCP 让 Claude、ChatGPT、VS Code 用同一套协议连接你的文件、数据库、搜索工具。

| | 没有 MCP | 有了 MCP |
|---|---|---|
| 接一个新工具 | 每家 AI 各写一遍适配 | 写一次，所有 MCP 客户端都能用 |
| 工具数量 | 10 个工具 = 10 套集成代码 | 10 个工具 = 10 个独立 server |
| 你的数据 | 要复制进对话上下文 | server 本地读，不进入上下文 |

---

## 三层结构（最容易搞混的地方）

MCP 分**参与者**和**层**两个维度，先记住参与者：

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  Host 应用  │         │   Client    │         │   Server    │
│ (Claude、   │ ◄─────► │  (协议客户端) │ ◄─────► │ (你的工具/  │
│  VS Code)   │  协议   │             │  协议   │  数据源)    │
└─────────────┘         └─────────────┘         └─────────────┘
     宿主                    桥梁                    能力提供方
```

- **Host（宿主应用）**：用户直接用的软件，如 Claude Desktop、VS Code、Cursor
- **Client（客户端）**：Host 内部负责协议通信的组件，一个 Host 可同时挂多个 Client
- **Server（服务端）**：你写的、暴露能力的程序，通常跑在本机或你自己的服务器

**常见误区**：以为 MCP 是"云服务 API"。不是——MCP 是一个**协议标准**，server 可以完全跑在你自己的机器上，数据不出本机。

### Server 提供三类原语

这是 server 的全部能力，没有第四种：

| 原语 | 谁控制 | 类比 | 用途 |
|---|---|---|---|
| **Tools（工具）** | 模型决定是否调用 | 函数 | 查天气、读数据库、发请求 |
| **Resources（资源）** | 应用/用户选择 | GET 请求 | 文件内容、日志、配置 |
| **Prompts（提示词）** | 用户主动触发 | 模板按钮 | "/总结这段代码" 这类预设 |

**判断标准**：想让模型自己决定用不用 → 做成 **Tool**；想让用户自己选看不看 → 做成 **Resource**。

---

## 10 分钟跑通第一个 Server

### 第 1 步：选 SDK

官方 SDK（<https://modelcontextprotocol.io/docs/sdk>）覆盖 TypeScript、Python、Java、Kotlin、C#、Go、Rust、Swift、Ruby、PHP。

Python 上手最快：

```bash
pip install mcp
```

### 第 2 步：写一个 30 行的 server

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-first-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """两数相加。docstring 会作为工具描述传给模型。"""
    return a + b

@mcp.resource("config://app")
def get_config() -> str:
    """应用配置，用户可在客户端里主动查看。"""
    return '{"env": "dev"}'

if __name__ == "__main__":
    mcp.run()   # 默认走 stdio 传输
```

三个要点：

1. **docstring 就是提示词**。模型只靠它理解这个工具干什么、参数什么意思。写"两数相加"比写"add function"有用得多。
2. **类型注解必须写**。SDK 从注解生成 JSON Schema，没有注解工具就废了。
3. **`mcp.run()` 默认 stdio**——server 通过标准输入输出跟客户端通信，不需要开端口。

### 第 3 步：接到客户端

以 Claude Desktop 为例，编辑配置文件 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "my-first-server": {
      "command": "python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

重启 Claude Desktop，对话框里应该能看到 `add` 工具出现。

### 第 4 步：验证

不会调或者报错时，用官方 **MCP Inspector** 调试：

```bash
npx @modelcontextprotocol/inspector
```

它是个浏览器里的交互工具，能逐条看请求响应、看工具列表、手动触发调用。**排查"客户端连不上"的问题，先用它，别在客户端里瞎试。**

---

## 传输方式：stdio 与 HTTP

| | stdio | Streamable HTTP |
|---|---|---|
| 适用 | 本机 server | 远程 server |
| 配置 | `command` + `args` | `url` |
| 认证 | 不需要（本机进程） | OAuth 2.1 |
| 场景 | 读本地文件、跑本地脚本 | 团队共享的服务 |

本机自用选 stdio，**不要给自己找麻烦开端口**。只有需要给别人用时才上 HTTP + OAuth。

---

## 安全：先看这几条再上线

MCP 让模型能"动手"，风险跟纯对话完全不是一个量级。官方安全文档（<https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>）列了完整的攻击向量，入门阶段记住四条就够：

1. **Confused Deputy（混淆代理）**：server 用高权限的自己的身份替用户办事，用户却被当成低权限的。**修法**：每个请求都校验用户实际权限，别用 server 的统一密钥。
2. **Token Passthrough（令牌透传）**：客户端把用户的 token 直接丢给 server，server 拿它去问别的服务。**修法**：server 不接受客户端传来的 token，自己走 OAuth。
3. **SSRF**：工具参数里带个 URL，server 就去请求——攻击者能让你的 server 打内网。**修法**：URL 白名单 + 禁私有地址段。
4. **本地 server 被劫持**：stdio server 跑在你机器上，进程被替换就能为所欲为。**修法**：只装来源可信的 server，别随手 `npx` 陌生包。

**一条通用原则**：MCP server 的权限 = 它跑在哪个身份下。把 server 当成"一个联网的可执行程序"来审，而不是"一个 API 封装"。

---

## 跟 Skills、Agent 的关系

这三个词经常一起出现，分工不同：

| 概念 | 本质 | 例子 |
|---|---|---|
| **MCP** | 连接协议（怎么把能力接进来） | filesystem server、github server |
| **Agent Skills** | 教 AI 做某类事的说明包（SKILL.md） | "按这个流程做代码评审" |
| **Agent 框架** | 编排多步任务 + 记忆 + 工具调度 | CrewAI、LangGraph |

顺序上：**先有 MCP 把工具接进来，再用 Skills 规定怎么用，最后 Agent 框架决定何时用哪个。**

---

## 常见坑

| 坑 | 症状 | 解法 |
|---|---|---|
| docstring 写得太简略 | 模型不知道何时调工具 | 写清"什么时候该用这个工具" |
| 忘了类型注解 | 工具出现在列表里但调用必失败 | 所有参数加注解 |
| 一个 server 塞 50 个工具 | 模型选择困难，误调用 | 按场景拆 server，单个 5–15 个工具 |
| 工具报错信息不返回 | 模型反复重试同一个错 | 异常也要作为工具结果返回，说清原因 |
| 用 stdio 却 print 调试 | 协议被污染，客户端直接断开 | 日志走 stderr，stdout 只给协议 |

---

## 本篇小结

- MCP = AI 应用的 USB-C，是**协议**不是云服务
- Server 提供三种原语：Tools（模型调）、Resources（用户选）、Prompts（模板）
- 本机用 stdio，远程才用 HTTP + OAuth
- 安全按"联网可执行程序"的标准审，重点防 confused deputy 和 SSRF
- 调试用 MCP Inspector，别在客户端里猜

**下一步**：想深入就读官方 [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture)（数据层协议细节）和 [Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)（完整攻击向量清单）。
