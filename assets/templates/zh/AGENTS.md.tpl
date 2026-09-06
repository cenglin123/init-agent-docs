# AI 协作规范

<!-- AGENTS.md 是主副本。编辑后运行：python scripts/agent_links.py repair -->
> 本文件会被 AI 框架自动加载并始终驻留在上下文中，因此必须保持精简（≤ 250 行）。
> 只放行为规则和信息指针，不放可从代码或其他文档获取的事实描述。

## 项目概述

<!-- 1–2 句话 -->

## 同步声明

`AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 内容必须保持一致。**只编辑 AGENTS.md**，另两个由脚本同步。

- `python scripts/agent_links.py check` / `repair` / `repair --force`
- 模式：copy

## 信息导航

<!-- 根据项目实际情况裁剪：不需要的删掉对应行；没有的文档不保留死链 -->
- 文档总索引：[docs/STRUCTURE.md](docs/STRUCTURE.md)
- 系统主线与设计决策：[docs/overview.md](docs/overview.md)
- API 约定：[docs/api.md](docs/api.md)
- 部署与同步：[docs/deployment.md](docs/deployment.md)
- 环境陷阱：[docs/pitfalls.md](docs/pitfalls.md)
- 文件格式约定（frontmatter schema）：[docs/frontmatter-schemas.md](docs/frontmatter-schemas.md)
- 文档一致性审计：[docs/audit-checklist.md](docs/audit-checklist.md)
- 复杂任务计划：[docs/plans/](docs/plans/)
- 当前任务状态：[docs/CURRENT.md](docs/CURRENT.md)
- 项目记忆索引：[.agents/memory/MEMORY.md](.agents/memory/MEMORY.md)
- Bugfix 档案：[docs/problems/bugfix/](docs/problems/bugfix/)
- 变更记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)

<!-- 省略声明：被裁剪的信息在此声明 -->

## 项目记忆

<!-- 中型+项目保留。小型项目删除本节及信息导航中记忆/Bugfix 行 -->
- **用户**：<!-- 称呼、关键偏好 -->
- **项目上下文**：<!-- 当前活跃项目的一句话描述 -->
- **最近教训**：<!-- 最重要的 1–2 条 -->
- **详细记忆**：[.agents/memory/MEMORY.md](.agents/memory/MEMORY.md)

> 维护细节（写入触发、touch 规范、索引重建）见 MEMORY.md 和 `python scripts/maintain.py`。

## 行为规则

### Compact 恢复

若上下文含 "continued from a previous conversation"：
1. 读 [docs/CURRENT.md](docs/CURRENT.md) — 确认当前任务状态
2. <!-- 非小型项目 --> 读 [.agents/memory/MEMORY.md](.agents/memory/MEMORY.md) — 恢复项目记忆
3. 上述完成前，**禁止写操作、禁止有副作用的判断**

### 任务前记忆检索

<!-- 中型+项目保留。小型项目删除本节 -->
除非任务非常简单明确，开始前先查经验系统：[.agents/memory/MEMORY.md](.agents/memory/MEMORY.md) 索引段 → 按需深入。
Bugfix 任务（修复 / bug / 报错 / 异常等）必须先查索引段的 bugfix 分区——检索动作必须发生，确认无相关记录才可继续。检索流程详情见 MEMORY.md。

### Bugfix 沉淀

<!-- 中型+项目保留。小型项目删除本节 -->
修复 bug、排查异常、处理回归完工时，必须沉淀一篇 `docs/problems/bugfix/<slug>.md`。触发条件不变：完工时必写；写作规范（frontmatter、复现、验证）见 [docs/problems/bugfix/_template.md](docs/problems/bugfix/_template.md)。逐篇索引由 `python scripts/maintain.py` 派生，不手工登记。

### 硬约束（不可违反）

<!-- 只保留项目特异的、无脚本兜底的约束。hooks/CI 已强制的事项不在此枚举。 -->
<!-- 候选项示例：密钥路径、构建产物路径、前后端同步规则。无则删除本节。 -->

### 默认偏好（有充分理由可偏离）

<!-- 候选项：只有目标仓库已有约束或用户确认时保留。 -->
- **先读后改**：修改任何文件前先读取，理解现有逻辑再动手。
- **Occam**：如无必要，勿增实体。
- **Bitter Lesson**：通用方法优于硬编码先验。
- **模式匹配**：单会话小任务用直接执行；跨模块/跨会话任务走「复杂任务闭环」：
  1. `docs/plans/active/` 落盘计划 → 2. subagent 审计 → 3. 用户确认 → 4. 执行 → 5. subagent 验收
- **任务启动先读 CURRENT.md**。
- **验证尽量换视角**：高风险改动优先由新上下文或 reviewer 视角复查。
<!-- 补充项目特异偏好（代码风格、语言约定等） -->

### 多 Agent worktree 路由（可选）

<!-- 仅协作倾向项目。按 SKILL.md 第 6.5 步安装后保留；否则整节删除 -->
- 普通写任务默认 `python scripts/worktree_task.py create` 获得独立 worktree。
- 四动作：`create` / `check <id>` / `integrate <id>` / `cleanup <id>`。详细语义见 `assets/references/workflow-patterns.md`。

## 测试要求

<!-- 按项目填写。无测试套件则写手动验证方式 -->

## 安全与配置

<!-- 可选。涉及密钥/认证/敏感数据时保留。 -->

## 提交规范

<!-- 候选项：按项目实际风格填写 -->
Conventional Commit（`feat:` / `fix:` / `chore:`）。治理文档修改须含 `[governance]` 标记。完成一个阶段后主动提交。

## 文档维护原则

1. **不重复**：同一信息只在最合适的位置出现一次
2. **只记代码/正文里读不出来的东西**：设计原因、协作约束、环境陷阱
3. **治理文档直接写最终态**：修改 AGENTS.md / STRUCTURE.md 等规则文件时不留「以前xx，现在xx」对比、日期标记或弃用标注——当前文本即权威；过程归 git log，制度变更归 CHANGELOG，两者已覆盖历史需求
4. **CHANGELOG**：用 `python scripts/changelog.py titles/show/add/recent`，不读全文
5. **计划落盘**：跨模块/跨会话的任务在 `docs/plans/active/` 写计划，完成后移 `completed/`
6. **定期审计**：每 ~20 次任务或每月，跑 `python scripts/audit.py check`（有记忆系统用 `python scripts/maintain.py`）

> docs/ 文件的治理规则（存在/合并/创建/删除条件）见 [docs/STRUCTURE.md](docs/STRUCTURE.md)「文件治理」段。

## 完工必检

```
python scripts/check_all.py --quiet
```

无输出 = 机械层通过。每条 FAIL 自带修复指引。

机械层通过后再确认：
- [ ] 有高风险改动且没经过独立视角复查？→ 新上下文或 subagent 复查
- [ ] 本次对话有值得沉淀的记忆？→ 更新 `.agents/memory/` 并同步 AGENTS 内联摘要<!-- 小型项目：整行替换为"小型项目，无记忆目录" -->
- [ ] 纯格式修改/注释修改/同一会话已记录？→ 文档更新可跳过（验证不跳过）
