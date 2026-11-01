# 文档一致性审计清单

> **何时触发**：`python scripts/audit.py check` 报告发现后，或每 ~20 次任务 / 每月主动执行一次。
> **角色**：本文件由 Agent 读取并填写，不是人类维护的文档。

<!-- ⓘ 本文档的治理规则见 AGENTS.md「文档维护原则」段及 docs/STRUCTURE.md「文件治理」段 -->

## 1. 机械检查结果复核

运行 `python scripts/audit.py check`，对每个非 OK 项逐条复核。

> **首次审计注意**：`audit.py` 内置的 DRIFT_PATTERNS 只覆盖 24 种常见技术栈。如果你的项目使用了不在字典中的技术（如 Cassandra、DynamoDB、NATS、SQS），应编辑 `scripts/audit.py` 的 `DRIFT_PATTERNS` 字典，追加项目实际使用的技术关键词。这是设计哲学第 8 条的预期行为——通用字典是起点，不是终点。

- [ ] 死链：是文件被移动了？还是 AGENTS.md 指针过时？
- [ ] STRUCTURE 索引偏差：docs/ 下多了/少了文件？更新索引或清理孤儿文件。
- [ ] 行数警告：AGENTS.md 超过 250 行？如有内容可下沉到 docs/，执行下沉。
- [ ] 依赖漂移：文档声明的技术栈与实际 manifest 不符？更新文档或确认为误报。
<!-- Git profile only -->
- [ ] 出生档案：缺失则从 Git history / 当前状态重建。
<!-- /Git profile only -->
<!-- no-Git profile only -->
- [ ] 出生档案：缺失则从 CHANGELOG / 当前文件状态重建。
<!-- /no-Git profile only -->
- [ ] 记忆系统：`.agents/memory/MEMORY.md` 空壳或断链？AGENTS.md 内联记忆段缺失或过时？`python scripts/audit.py memory` 逐项复核。

- [ ] 残留同步机制（迁移场景）：`scripts/agent_links.py` 已删除？根目录无 `CLAUDE.md` / `GEMINI.md` 残留副本？任一存在即清退并记录。
<!-- Git profile only -->
- [ ] 残留同步 hook（迁移场景）：`.githooks/pre-commit` 与 `.pre-commit-config.yaml` 已移除对同步脚本的调用段——脚本已删除而 hook 仍调用会卡死提交路径。
<!-- /Git profile only -->

## 2. 关键设计决策仍成立？

重新读取 `docs/overview.md` 中"关键设计决策"段，逐条验证：

- [ ] 对每条决策中提到的技术栈，检查 manifest（`package.json` / `pyproject.toml` 等）中是否仍有对应依赖。若文档说"使用 SQLite"，但 manifest 中已无 sqlite 相关依赖 → 决策已过时，标注"已过时（YYYY-MM-DD）"并记录替代方案。
<!-- Git profile only -->
- [ ] 对每条决策中提到的约束条件（如"单机部署"、"数据量 < 10GB"），用 `git log --oneline --since="6 months ago"` 检查是否有相关的基础设施变更。若有重构/迁移类 commit → 约束可能已失效，需更新。
<!-- /Git profile only -->
<!-- no-Git profile only -->
- [ ] 对每条决策中提到的约束条件，结合 CHANGELOG、CURRENT 和相关文件修改时间检查是否有基础设施变更；存在重构或迁移记录时重新验证约束。
<!-- /no-Git profile only -->
- [ ] 是否有新的重要决策未记录？浏览最近 CHANGELOG 中涉及架构/基础设施的变更，确认已反映到 `docs/overview.md`。

## 3. 环境与部署仍准确？

- [ ] 环境变量列表与当前 `.env.example` / config 一致？
- [ ] 启动命令仍能执行？
- [ ] 持久化路径 / 备份策略描述是否仍然准确？

## 4. 未记录的重要变更

- [ ] 浏览 CHANGELOG 最近 ~30 天：`python scripts/changelog.py recent --days 30`，是否有架构级变更未反映到 docs/？
<!-- Git profile only -->
- [ ] `git log --oneline --since="1 month ago"` 中是否有被遗漏的重大改动？
<!-- /Git profile only -->
<!-- no-Git profile only -->
- [ ] CURRENT、CHANGELOG 和近一个月修改的关键文件中是否有被遗漏的重大改动？
<!-- /no-Git profile only -->

## 5. 完工

- [ ] 审计期间的修改已通过 `python scripts/check_all.py --quiet`
- [ ] 未决债务已清点：逐条处置（收敛 / 放弃 / 继续挂），收敛与放弃均已行尾标注（见「未决债务登记」段）
- [ ] 审计结果写入 CHANGELOG：
  ```bash
  python scripts/changelog.py add \
    --title "文档一致性审计" \
    --body "机械检查 + 手动裁决完成。修复项：<列出>；确认为误报：<列出>；仍待处理：见「未决债务登记」段（本日 N 条）"
  ```
- [ ] 将审计日期记录到本文件末尾的"审计记录"中

## 未决债务登记

> 文档收敛类待办（评审 / 审计遗留的低优先未修项、口径待补、待收敛项）登记于此；能指认稳定出处才入册。
> 业务挂账（任务遗留、待补处理）不进本段：走 `docs/plans/active/` 或项目 issue 系统；CHANGELOG 只记"为什么没做"。
> **本段必须位于「审计记录」段之前**——审计触发器只解析「审计记录」段之后的窗口，债务条目日期不得进入该窗口。

- 登记格式：`日期 ｜ 位置 ｜ 内容一行（出处：CHANGELOG 日期 / 变更记录条目 / bugfix slug / 计划文件名）`
- 只追加新行；**销账 = 仅在既有行尾追加 `→ 已销账 YYYY-MM-DD（处置）` 标注，不得改写既有文字**
- 处置三选一并行尾标注：收敛 → `→ 已销账`；放弃 → 同样行尾标注并注明「不再修」及原因；继续挂 → 保留原行
- 每次审计逐条清点；无变化的债务合并记一行「其余 N 条继续挂，无变化」
- 计划「风险与遗留」中的文档收敛类项在计划归档时转入本段
- 本段与「审计记录」同属记录性编辑：登记 / 销账不触发治理文档分层复查；改本段规则文字才触发

<!-- 登记示例：2026-11-01 ｜ docs/overview.md ｜ [待收敛内容]（出处：CHANGELOG 2026-11-01）；首条登记后删除本注释 -->

## 审计记录

<!-- 每次完成审计后在此追加一条记录，格式：YYYY-MM-DD — 审计摘要（发现/修复/遗留） -->
