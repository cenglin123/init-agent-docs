# CHANGELOG

## [今天的日期，如 2026-04-17]

### 初始化文档体系

- 创建 agent-first 文档结构：AGENTS.md（含硬链接）+ STRUCTURE.md + docs/ 层级
- 配置 scripts/changelog.py 与 scripts/agent_links.py，脚本化维护日志和硬链接
- 设计哲学：仓库即事实源，只记代码读不出来的东西，计划作为跨上下文交接协议

<!--
说明：
- 日期节倒序，最新在前。同一天的多次修改合并到同一个日期节，用 ### 区分主题。
- 写入前不要读全文，用 `python scripts/changelog.py titles/show/add` 查看标题树、局部读取和追加。
- 当前工作状态写在 docs/CURRENT.md；CHANGELOG 只记录历史变更。
-->
