# AI 协作规范

<!-- AGENTS.md 是唯一入口；由宿主实际配置决定加载与可见性，不创建同步副本。 -->
> 本文件作为项目行为入口，必须保持精简（≤ 250 行）；实际加载、常驻与可见性取决于宿主配置，不保证模型遵守。
> 只放行为规则和信息指针，不放可从代码或其他文档获取的事实描述。

## 项目概述

<!-- 1–2 句话 -->

## 信息导航

<!-- 根据项目实际情况裁剪：不需要的删掉对应行；没有的文档不保留死链 -->
<!-- Medium/Large profile only -->
- 文档总索引：[docs/STRUCTURE.md](docs/STRUCTURE.md)
- 系统主线与设计决策：[docs/overview.md](docs/overview.md)
- API 约定：[docs/api.md](docs/api.md)
- 部署与同步：[docs/deployment.md](docs/deployment.md)
- 环境陷阱：[docs/pitfalls.md](docs/pitfalls.md)
- 文件格式约定（frontmatter schema）：[docs/frontmatter-schemas.md](docs/frontmatter-schemas.md)
<!-- /Medium/Large profile only -->
- 文档一致性审计：[docs/audit-checklist.md](docs/audit-checklist.md)
<!-- Medium/Large profile only -->
- 治理合同：[docs/governance.md](docs/governance.md)
- 复杂任务计划：[docs/plans/](docs/plans/)
<!-- /Medium/Large profile only -->
- 当前任务状态：[docs/CURRENT.md](docs/CURRENT.md)
<!-- Medium/Large profile only -->
- 项目记忆索引：[.agents/memory/MEMORY.md](.agents/memory/MEMORY.md)
- Bugfix 档案：[docs/problems/bugfix/](docs/problems/bugfix/)
<!-- /Medium/Large profile only -->
- 变更记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)

<!-- 省略声明：被裁剪的信息在此声明 -->

<!-- Small profile only -->
- 初始化出生档案：[docs/initialization.md](docs/initialization.md)
<!-- /Small profile only -->

<!-- Medium/Large profile only -->
## 项目记忆

<!-- 中型+项目保留。小型项目删除本节及信息导航中记忆/Bugfix 行 -->
- **用户**：<!-- 称呼、关键偏好 -->
- **项目上下文**：<!-- 当前活跃项目的一句话描述 -->
- **最近教训**：<!-- 最重要的 1–2 条 -->
- **经验检索**：`python scripts/maintain.py --memory-search "关键词" --limit 5`；按命中链接读原文，完整索引按需读取。

> 维护细节（写入触发、touch 规范、索引重建）见 MEMORY.md 和 `python scripts/maintain.py`。

<!-- /Medium/Large profile only -->

## 行为规则

### Compact 恢复

若上下文含 "continued from a previous conversation"：
1. 读 [docs/CURRENT.md](docs/CURRENT.md) — 确认当前任务状态
<!-- Medium/Large profile only -->
2. 按 CURRENT 中任务关键词运行 `python scripts/maintain.py --memory-search "关键词" --limit 5`，按需读命中原文；不默认全文加载累积索引。
<!-- /Medium/Large profile only -->
3. 上述完成前，**禁止写操作、禁止有副作用的判断**

<!-- Medium/Large profile only -->
### 任务前记忆检索

<!-- 中型+项目保留。小型项目删除本节 -->
除非任务非常简单明确，开始前运行 `python scripts/maintain.py --memory-search "任务关键词" --limit 5`，按命中链接深入；截断时换词或调整 limit，完整索引按需读。
Bugfix 任务（修复 / bug / 报错 / 异常等）须检索相关经验，检索覆盖记忆与 bugfix 分区；无相关记录也可继续。检索流程详情见 MEMORY.md。

### Bugfix 沉淀

<!-- 中型+项目保留。小型项目删除本节 -->
修复具有可复用教训、发生复发、涉及高风险或用户要求时，在 `docs/problems/bugfix/<slug>.md` 留专篇；其余在现有任务记录或 CHANGELOG 留必要验证证据。写作规范见 [docs/problems/bugfix/_template.md](docs/problems/bugfix/_template.md)；经验写入、修改、移动或删除后，同一任务运行 `python scripts/maintain.py --memory-index` 刷新派生入口，无需为此运行全量维护审计。

<!-- /Medium/Large profile only -->

### 硬约束（不可违反）

<!-- 只保留项目特异的、无脚本兜底的约束。hooks/CI 已强制的事项不在此枚举。 -->
<!-- 候选项示例：密钥路径、构建产物路径、前后端同步规则。无则删除本节。 -->

### 默认偏好（有充分理由可偏离）

<!-- 候选项：只有目标仓库已有约束或用户确认时保留。 -->
- **先读后改**：修改任何文件前先读取，理解现有逻辑再动手。
- **Occam**：如无必要，勿增实体。
- **Bitter Lesson**：通用方法优于硬编码先验。
- **模式匹配**：单会话小任务用直接执行；跨模块/跨会话任务走当前选定的控制器下的「复杂任务闭环」：
  记录范围与验收 → 独立视角审查 → 在已有授权内执行 → 验收；已有授权不重复确认。
<!-- Medium/Large profile only -->
  跨会话详细计划写入 `docs/plans/active/`。
<!-- /Medium/Large profile only -->
<!-- Small profile only -->
  任务和交接写 CURRENT，规则改进候选写审计清单。
<!-- /Small profile only -->
- **任务启动先读 CURRENT.md**。
- **验证尽量换视角**：高风险改动必须由新上下文或 reviewer 视角独立复查。
<!-- 补充项目特异偏好（代码风格、语言约定等） -->

<!-- Medium/Large profile only -->
<!-- Git profile only -->
### 多 Agent worktree 路由（可选）

<!-- 仅 Git profile 的协作倾向项目按初始化可选集成流程安装后保留；否则整节删除 -->
- **主工作树归持有 main-claim 的 agent**（通常是主对话/primary）：开工前 `python scripts/worktree_task.py claim-main --owner primary`，收工 `release-main --owner primary`；忘记释放由 TTL（默认 180 分钟）自动过期兜底。
- **fork / 子代理一律开 worktree，无例外**：入场即 `create` 并按下方流程登记。不要以「主工作树干净」作为可直接工作的依据——两次写文件之间它总是干净的，时点快照防不了撞车（两个守规 agent 仍会碰撞）。
- 普通写任务用 `python scripts/worktree_task.py create --name <显示名> --owner <标识>` 获得独立 worktree；显示名只输入一次，续办凭 ID、owner、generation 执行 `resume`，不按时间抢占。
- 写前登记 `intent` 的目标、非目标、自由范围并 `review` 全部未关闭任务；路径重叠仅作提示。相关双方确认同一协议、重新 review 后 `admit`，再主动 `check <id> --write`。范围变化重新入场；未登记旧任务视为 unknown。
- **`integrate` 在存在他人活动 main-claim 时机械拒绝**（对方可能正在写主工作树）——被拒就协调或等待过期，不要强夺。
- worktree 仅隔离未提交内容与 index，不消除合入、语义或外部系统冲突。此入口是协作软约束，不能拦截直接文件写入或手动 Git；owner/override 声明不是身份认证或外部授权。`integrate`、`close`、`cleanup` 的清理与审计边界见 `python scripts/worktree_task.py --help` 和本项目协作说明。
<!-- /Git profile only -->

<!-- /Medium/Large profile only -->

## 测试要求

<!-- 按项目填写。无测试套件则写手动验证方式 -->

## 安全与配置

<!-- 可选。涉及密钥/认证/敏感数据时保留。 -->

<!-- Git profile only -->
## 提交规范

<!-- 候选项：按项目实际风格填写 -->
<!-- 按项目实际风格选择；提交/发布依用户授权，不因阶段完成自动执行。 -->
Conventional Commit（`feat:` / `fix:` / `chore:`）。治理文档修改须含 `[governance]` 标记。提交、推送与发布按既有授权处理。
<!-- /Git profile only -->

## 文档维护原则

1. **不重复**：同一信息只在最合适的位置出现一次
2. **只记代码/正文里读不出来的东西**：设计原因、协作约束、环境陷阱
3. **治理文档直接写最终态**：修改项目规则文件时不留「以前xx，现在xx」对比、日期标记或弃用标注——当前文本即权威；过程性历史按当前 profile 的历史入口维护，制度变更归 CHANGELOG
4. **CHANGELOG**：用 `python scripts/changelog.py titles/show/add/recent`，不读全文
<!-- Medium/Large profile only -->
5. **计划落盘**：跨模块/跨会话的任务在 `docs/plans/active/` 写计划，完成后移 `completed/`
6. **定期审计**：每 ~20 次任务或每月，跑 `python scripts/maintain.py`。
<!-- /Medium/Large profile only -->
<!-- Small profile only -->
5. **任务状态**：任务与交接写 CURRENT，出生档案不被普通任务覆盖。
6. **定期审计**：每 ~20 次任务或每月，跑 `python scripts/audit.py check`。
<!-- /Small profile only -->

<!-- Medium/Large profile only -->
> docs/ 文件的治理规则（存在/合并/创建/删除条件）见 [docs/STRUCTURE.md](docs/STRUCTURE.md)「文件治理」段。

<!-- /Medium/Large profile only -->

<!-- Small profile only -->
### 文件治理

docs 文件只在能回答入口无法承载的问题时创建；优先并入已有文件，足够短且应常见的内容内联 AGENTS。迁移完成无引用或内容无效时删除，制度变更记 CHANGELOG，不留弃用标注。

### 治理闭环

<!-- 从治理合同 small-contract 标记段提取正文并绑定本项目命令；不手维护第二份摘要。 -->
<!-- /Small profile only -->

## 完工必检

<!-- Medium/Large profile only -->
```
python scripts/check_all.py --quiet
```
<!-- /Medium/Large profile only -->
<!-- Small profile only -->
```
python scripts/check_all.py --quiet --small
```
<!-- /Small profile only -->

无输出 = 机械层通过。每条 FAIL 自带修复指引。

机械层通过后再确认：
- [ ] 有高风险改动且没经过独立视角复查？→ 新上下文或 subagent 复查
- [ ] 触及治理文档（入口、流程、hook、审计脚本等被作为规则消费的文件）的规则？→ 无论行数须一次独立视角复查，记录基线、发现与裁决；遵从项目已有更严格要求。纯记录编辑（债务登记/销账、审计记录、候选状态/证据/验证/拒绝/观察）豁免，改变判据或行为仍须复查。
- [ ] 执行中发现文档断言与实机不符？→ 先判定哪侧错，再修正该处 + 核对同维度其余断言（细节见 docs/audit-checklist.md 触发段；结论记计划完成记录/CHANGELOG，不写「审计记录」段的日期字面量）
- [ ] 评审 / 审计 / 执行中发现留下文档收敛类遗留？→ 登记到 docs/audit-checklist.md「未决债务登记」段（业务挂账走项目当前任务记录，不进债务段）
<!-- Medium/Large profile only -->
- [ ] **记忆自检**：本次对话有值得沉淀的记忆？→ 更新 `.agents/memory/` 并同步 AGENTS 内联摘要；命中并实际遵循的经验按 MEMORY.md「确认 touch」更新确认字段。经验变动后运行 `python scripts/maintain.py --memory-index`。
<!-- /Medium/Large profile only -->
- [ ] 纯格式修改/注释修改/同一会话已记录？→ 文档更新可跳过（验证不跳过）
