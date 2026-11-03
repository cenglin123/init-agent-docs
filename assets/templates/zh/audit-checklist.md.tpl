# 文档一致性审计清单

> **何时触发**：`python scripts/audit.py check` 报告发现后，或每 ~20 次任务 / 每月主动执行一次；执行中发现文档断言与实机不符时做局部核对——先判定哪侧错（无法判定只登记债务、不修正），再修正该处（修正治理文档断言后仍须独立复查）+ 核对同维度断言（其他文档同源断言一并纳入）；同维度失效 ≥2 或总失效 ≥3、或涉及决策 / 环境类 → 转全量审计；核对成本超单文档单维度且断言数超项目上限时，未核部分登记本文件债务段。局部核对不写本文件「审计记录」段的日期字面量（登记债务不受限），结论记计划完成记录/CHANGELOG，不销警。
> **角色**：本文件由 Agent 读取并填写，不是人类维护的文档。

<!-- 文件治理按 profile：Small 见 AGENTS.md；中大型见 STRUCTURE。生成后删除本注释。 -->

## 1. 机械检查结果复核

运行 `python scripts/audit.py check`，对每个非 OK 项逐条复核。

> **依赖提示口径**：关键词匹配只作 advisory，不阻断检查。标准库、系统设施及外部服务不一定在应用 manifest 中声明；Agent 按实际依赖和部署事实裁决，不靠扩充字典代替语义判断。坏文件、死链和必需资产缺失仍失败。

- [ ] 死链：是文件被移动了？还是 AGENTS.md 指针过时？
<!-- Medium/Large profile only -->
- [ ] STRUCTURE 索引偏差：docs/ 下多了/少了文件？更新索引或清理孤儿文件。
<!-- /Medium/Large profile only -->
- [ ] 行数警告：AGENTS.md 超过 250 行？如有内容可下沉到 docs/，执行下沉。
- [ ] 依赖漂移：文档声明的技术栈与实际 manifest 不符？更新文档或确认为误报。
<!-- Git profile only -->
- [ ] 出生档案：缺失则从 Git history / 当前状态重建。
<!-- /Git profile only -->
<!-- no-Git profile only -->
- [ ] 出生档案：缺失则从 CHANGELOG / 当前文件状态重建。
<!-- /no-Git profile only -->
<!-- Medium/Large profile only -->
- [ ] 记忆系统：`.agents/memory/MEMORY.md` 空壳或断链？AGENTS.md 内联记忆段缺失或过时？`python scripts/audit.py memory` 逐项复核。

<!-- /Medium/Large profile only -->

- [ ] 残留同步机制（迁移场景）：`scripts/agent_links.py` 已删除？根目录无 `CLAUDE.md` / `GEMINI.md` 残留副本？任一存在即清退并记录。
<!-- Git profile only -->
- [ ] 残留同步 hook（迁移场景）：`.githooks/pre-commit` 与 `.pre-commit-config.yaml` 已移除对同步脚本的调用段——脚本已删除而 hook 仍调用会卡死提交路径。
<!-- /Git profile only -->

## 2. 关键设计决策仍成立？

<!-- Medium/Large profile only -->
重新读取 `docs/overview.md` 中"关键设计决策"段，逐条验证：

- [ ] 对技术栈决策核对 manifest、标准库及实际部署设施；例如 SQLite 可由标准库提供，外部数据库可独立部署。仅关键词缺失不能判过时；确认事实变化后才改写决策并记 CHANGELOG。
<!-- Git profile only -->
- [ ] 对每条决策中提到的约束条件（如"单机部署"、"数据量 < 10GB"），用 `git log --oneline --since="6 months ago"` 检查是否有相关的基础设施变更。若有重构/迁移类 commit → 约束可能已失效，需更新。
<!-- /Git profile only -->
<!-- no-Git profile only -->
- [ ] 对每条决策中提到的约束条件，结合 CHANGELOG、CURRENT 和相关文件修改时间检查是否有基础设施变更；存在重构或迁移记录时重新验证约束。
<!-- /no-Git profile only -->
- [ ] 是否有新的重要决策未记录？浏览最近 CHANGELOG 中涉及架构/基础设施的变更，确认已反映到 `docs/overview.md`。

<!-- /Medium/Large profile only -->
<!-- Small profile only -->
核对 AGENTS 与 README 中的决策和实际 manifest / 命令是否一致；新决策归现有入口，不为审计预建专题。
<!-- /Small profile only -->

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

<!-- Medium/Large profile only -->
- [ ] 审计期间的修改已通过 `python scripts/check_all.py --quiet`
<!-- /Medium/Large profile only -->
<!-- Small profile only -->
- [ ] 审计期间的修改已通过 `python scripts/check_all.py --quiet --small`
<!-- /Small profile only -->
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
<!-- Medium/Large profile only -->
> 业务挂账不进本段：走 `docs/plans/active/` 或项目 issue 系统。
<!-- /Medium/Large profile only -->
<!-- Small profile only -->
> 业务挂账不进本段：走 docs/CURRENT.md；规则改进候选写下节，不写出生档案。
<!-- /Small profile only -->
> CHANGELOG 只记为什么没做。
> **本段必须位于「审计记录」段之前**——审计触发器只解析「审计记录」段之后的窗口，债务条目日期不得进入该窗口。

- 登记格式：`日期 ｜ 位置 ｜ 内容一行（出处：稳定的任务记录或 CHANGELOG 条目）`；执行不符的未核项，出处填本次任务记录或 CHANGELOG 条目
- 只追加新行；**销账 = 仅在既有行尾追加 `→ 已销账 YYYY-MM-DD（处置）` 标注，不得改写既有文字**
- 处置三选一，均按同一格式行尾标注：收敛 → `→ 已销账 YYYY-MM-DD（已修）`；放弃 → `→ 已销账 YYYY-MM-DD（不再修：原因）`；继续挂 → 保留原行不标注
- 每次审计逐条清点；无变化的债务在段末合并记一行 `YYYY-MM-DD ｜ 其余 N 条继续挂，无变化`（N = 未销账且非合并行的登记行数；合并行不记位置字段；旧合并行由新行取代时，在旧行尾追加「→ 已被 YYYY-MM-DD 合并行取代」）
<!-- Medium/Large profile only -->
- 计划「风险与遗留」中的文档收敛类项在计划归档时转入本段
<!-- /Medium/Large profile only -->
- 本段与「审计记录」同属记录性编辑：登记 / 销账不触发治理文档分层复查；改本段规则文字才触发

<!-- 登记示例：2026-11-01 ｜ docs/overview.md ｜ [待收敛内容]（出处：CHANGELOG 2026-11-01）；首条登记后删除本注释 -->

## 改进候选与验证

> 按项目治理合同记录改变规则的候选：问题出处、范围、冻结基线与验收、保护场景、预算/重试/停止、独立验收与保留任务回归、成本/副作用、结果、采用/拒绝/观察/撤回。没有候选时不预建实体；记录不改写合同本身。
> 本段位于审计记录前；候选结果不是全量审计日期。CURRENT 只指本记录，不重复候选状态。
> 候选状态、证据、验证、拒绝、观察等纯记录编辑与债务/审计记录同属复查豁免；修改行为或判据仍按治理规则独立复查。

## 审计记录

<!-- 每次完成审计后在此追加一条记录，格式：YYYY-MM-DD — 审计摘要（发现/修复/遗留） -->
