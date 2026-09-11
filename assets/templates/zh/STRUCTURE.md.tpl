# [项目名] — STRUCTURE

> 本文件只做架构文档索引。协作规则和完工检查统一以 [AGENTS.md](../AGENTS.md) 为准。
> 治理规则（存在/合并/创建/删除条件）见文末「文件治理」段。

<!-- ⓘ 本文档仅 Medium/Large profile 创建。Small profile 不建此文件。 -->

| 需要了解 | 文件 |
|---------|------|
| 系统主线、设计决策 | [overview.md](overview.md) |
| API 接口 | [api.md](api.md)（如有） |
| 部署与配置 | [deployment.md](deployment.md) |
| 已知环境陷阱 | [pitfalls.md](pitfalls.md)（如有） |
| 文件格式约定（frontmatter schema） | [frontmatter-schemas.md](frontmatter-schemas.md)（如有） |
| Bugfix 档案 | [problems/bugfix/](problems/bugfix/)（逐篇索引见 MEMORY.md，不逐篇登记到本表） |
| 文档一致性审计 | [audit-checklist.md](audit-checklist.md) |
| 当前任务状态 | [CURRENT.md](CURRENT.md) |
| 变更记录 | [CHANGELOG.md](CHANGELOG.md) |

<!-- Git profile only -->
## 历史考古

需要追溯文档或代码的历史变更时：

- **文件变更历史**：`git log -- <文件路径>`
- **逐行追溯**：`git blame <文件路径>`
- **查找特定变更**：`git log --grep="<关键词>"`

`git log` 是考古信息的唯一合法归宿；文档正文不承载历史态信息。
<!-- /Git profile only -->

<!-- no-Git profile only -->
## 历史考古

非 Git 项目没有版本控制历史。追溯变更的方式：

- **变更记录**：查阅 [CHANGELOG.md](CHANGELOG.md) 了解重大变更
- **当前状态**：查阅 [CURRENT.md](CURRENT.md) 了解任务流转
- **文件时间戳**：文件系统的修改时间可作为粗略参考（精度有限）

重要变更应主动记录到 CHANGELOG，而非依赖版本控制历史。

<!-- /no-Git profile only -->

## 文件治理

以下规则定义 docs/ 下每个文件的存在条件、合并条件和创建/删除原则。

**存在条件**：每个 docs/ 文件的存在条件是它能回答一个 AGENTS.md 无法承载的"为什么"问题。不存在条件则不创建。条件消散则合并或删除。

**合并条件**（何时并入 AGENTS.md）：当文件内容足够短、内联不会明显增加 AGENTS.md 的认知负担、且 AGENTS.md 行数未超过 250 行时，内联优于独立文件。当文件的唯一读者是 Agent 且信息在每次对话中都应可见时，应内联。

**创建原则**：新增前必须说清它解决的具体问题（Occam）。优先用 AGENTS.md 已有段落或现有 docs/ 文件容纳信息；仅在现有结构无法容纳时才新建。

**删除原则**：内容已迁移且无残留引用 → 直接删除。

<!-- Git profile only -->
内容过时且 git log 可追溯 → 删除，不保留弃用标注。
<!-- /Git profile only -->
<!-- no-Git profile only -->
内容过时且 CHANGELOG 有记录 → 删除，不保留弃用标注。无版本历史时，确认内容确实无用后删除。
<!-- /no-Git profile only -->

信息已自然融入 AGENTS.md → 删除，并在 AGENTS.md 指针段中移除对应行。

**规范态原则**：治理文档（AGENTS.md、STRUCTURE.md 等规则文件）修改时直接改写为最终态——正文不携带「以前xx，现在xx」对比、日期标记、弃用标注。读者（每次冷启动的 Agent）只消费当前规则；

<!-- Git profile only -->
演化过程归 git log，制度变更归 CHANGELOG，正文与两者职责分离。
<!-- /Git profile only -->
<!-- no-Git profile only -->
演化过程归 CHANGELOG，正文与 CHANGELOG 职责分离。
<!-- /no-Git profile only -->
