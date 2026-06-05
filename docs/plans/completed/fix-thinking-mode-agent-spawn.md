# 修复 thinking mode 下 API 报错(thinking 回传 / system 角色)

> 创建时间：2026-05-29
> 状态：✅ 已定位根因并处置(回退 Claude Code 至 2.1.153 + 关闭自动升级)
> 模式：直接执行
> 协调人：chenr

## 目标

修复 Claude Code 会话中出现的两类 400 错误:
1. `API Error: 400 The content[].thinking in the thinking mode must be passed back to the API`
2. `API Error: 400 Failed to deserialize the JSON body ... messages[1].role: unknown variant 'system', expected 'user' or 'assistant'`

二者都导致对话中断,在思考模式下使用工具调用 / Agent spawn 时触发。

## 根因(已确认,带证据)

排查的关键事实源是 **cc-switch 的本地代理日志**(`C:\Users\chenr\.cc-switch\cc-switch.db` → `proxy_request_logs`)。

### 核心结论

错误**不是**本仓库、skill、plan 假设的问题,而是**第三方 provider 路径**导致。用户通过 cc-switch 把 Claude Code 路由到第三方 `/anthropic` 兼容端点(DeepSeek / Zhipu GLM / MiniMax 等),这些端点未忠实实现 Anthropic 协议,Claude Code 的不同请求形态会逐一暴露其不兼容点。

### 三类错误的分层归属

| 错误 | 归属 | 证据 |
|------|------|------|
| `content[].thinking must be passed back` | DeepSeek `/anthropic` 端点**未实现**「带签名 thinking 块在工具回合里往返」的契约 | 日志中 200/400 成对出现(生成 thinking=200,回传 thinking=400);**2.1.156 已修复客户端"改写 thinking 块"的 bug,但 DeepSeek 仍 400**,证明这是端点侧而非客户端侧 |
| `messages[].role=system` 反序列化失败 | 第三方端点的 **OpenAI 格式 ↔ Anthropic 格式不匹配**(system 当成 messages 数组里一条消息,而 Anthropic 端点只认 user/assistant) | serde 风格错误,非 Anthropic 的 Pydantic 错误;且未进 cc-switch 代理日志,疑似报错窗口带着旧 provider 的 env |
| (客户端侧)2.1.154/155 在 Opus 4.8 下改写 thinking 块 | **Claude Code 真实 bug**,Anthropic 已在 **2.1.156** 修复 | release note:"Fixed an issue when using Opus 4.8 where thinking blocks were modified, leading to API errors" |

### 触发时间线(决定性证据)

- **5-25 ~ 5-28**:DeepSeek 全程 200(5-28 有 158 次成功),无任何 400。
- **5-29 08:42:58**:第一个 400 出现。
- `~/.local/share/claude/versions/2.1.154` 二进制时间戳 = **5-29 08:42** —— 与首个 400 几乎同秒吻合。
- 结论:**今早自动升级到 2.1.154(引入 Opus 4.8 + 高 effort 默认开思考)那一刻打挂了 DeepSeek。** 2.1.153 及更早为最后已知可用版本。

### 被推翻的原始假设

原 plan 的假设 A(Claude Code 与 Agent 工具不兼容)、B(skill 注入破坏)、C(版本 bug 泛指)、D(上下文截断)**均不成立**。真正变量是第三方 provider 的兼容层 + 触发它的客户端版本变化。

## 最终处置(已执行)

用户选择回退而非改 provider env:

1. **回退 Claude Code 至 2.1.153**(缓存命中,无需下载):
   ```
   claude install 2.1.153 --force
   ```
   验证:`claude --version` → 2.1.153,二进制 235564192 字节。
2. **关闭自动升级**(双保险):
   - `setx DISABLE_AUTOUPDATER 1`(持久用户环境变量)
   - `~/.claude/settings.json` 的 `env` 加 `"DISABLE_AUTOUPDATER": "1"`
3. 生效需**完全重启** Claude Code 窗口(当前进程仍在内存中跑 2.1.156)。

## 决策记录

- 2026-05-29:将此问题从 converge 审查中分离优先处理——否则依赖 Agent spawn 的审查机制被阻塞。
- 2026-05-29:cc-switch 当前激活 provider 在 Claude Official ↔ DeepSeek 间多次切换;注意切 provider 后必须重启 Claude Code,env 在启动时注入,不会热更新。
- 2026-05-29:用户在「改 DeepSeek env 关思考(MAX_THINKING_TOKENS=0)」与「回退客户端版本」之间选择后者,选定 2.1.153(而非最初设想的 2.1.148,因 2.1.153 是缓存内、日志证实的最后可用版本)。

## 待验证(重启后)

切到 DeepSeek、开思考模式跑一个触发工具调用的小任务,查日志确认无新增 400:
```
sqlite3 cc-switch.db "SELECT datetime(created_at,'unixepoch','localtime'), status_code FROM proxy_request_logs WHERE provider_id='36d94358-0c39-4439-82cb-8163a7ef6f98' AND status_code=400 ORDER BY created_at DESC LIMIT 3;"
```
最新 400 仍停在 `2026-05-29 11:24:03`(无新增)即为成功。

## 风险与遗留

- 2.1.153 没有 Opus 4.8,也没有 2.1.156 的 thinking-block 客户端修复——但 DeepSeek 路径映射到 `deepseek-v4-pro`、用不到 4.8,无实质损失。
- `DISABLE_AUTOUPDATER` 只挡后台自动更新;若版本仍被顶上去,追加 `DISABLE_UPDATES=1`(更强,但会连手动 `claude install` 一并挡掉)。
- 想用官方 + Opus 4.8 + Agent/converge 时,临时移除 `DISABLE_AUTOUPDATER` 升级回去即可。
- 第三方 `/anthropic` provider(DeepSeek/GLM/MiniMax)对 Claude Code 完整特性的兼容是"打地鼠";要完整能力优先用 Claude Official。
