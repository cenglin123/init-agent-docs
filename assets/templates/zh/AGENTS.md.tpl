# AI 协作规范

<!-- AGENTS.md 是主副本。编辑后运行：python scripts/agent_links.py repair -->
> 本文件会被 AI 框架自动加载并始终驻留在上下文中，因此必须保持精简。
> 只放行为规则和信息指针，不放可从代码或其他文档获取的事实描述。
> 最终生成 AGENTS.md 前逐条过滤：每条内容必须满足下列至少一项，否则删除或下沉到 docs/。
> 1. 目标仓库事实源支持；2. 用户明确确认；3. 本 skill 创建的机制需要 Agent 记住；4. Agent 高概率会遗漏且遗漏代价高。

## 项目概述

<!-- 1–2 句话说明这个项目做什么。新 Agent 加载本文件后，应能立刻理解项目边界和核心价值。 -->
<!-- 示例：一个基于 React + Node.js 的全栈电商后台，核心功能包括商品管理、订单处理和支付对接。 -->

## 同步声明

`AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 内容必须保持一致；读取时选择其一即可。**只编辑 AGENTS.md**，另两个由脚本同步。

- 检查：`python scripts/agent_links.py check`
- 修复：`python scripts/agent_links.py repair`
- 强制覆盖（仅在人工确认 `CLAUDE.md` / `GEMINI.md` 改动可被 AGENTS.md 覆盖时）：`python scripts/agent_links.py repair --force`

<!-- 同步模式：默认 copy（最可靠，不受编辑器原子写入影响）。
     如文件系统支持且你理解 hardlink 的局限性，可改用 `--mode=hardlink`。
     在所有 check/repair 命令后追加 `--mode=copy` 或 `--mode=hardlink` 锁定模式。 -->
本项目使用 copy 模式。

## 信息导航

- 文档总索引：[docs/STRUCTURE.md](docs/STRUCTURE.md)
- 系统主线与设计决策：[docs/overview.md](docs/overview.md)
- API 约定：[docs/api.md](docs/api.md)
- 部署与同步：[docs/deployment.md](docs/deployment.md)
- 环境陷阱：[docs/pitfalls.md](docs/pitfalls.md)
- 文档一致性审计：[docs/audit-checklist.md](docs/audit-checklist.md)
- 复杂任务计划：[docs/plans/](docs/plans/)
- 当前任务状态（单 owner 摘要 / 全局入口）：[docs/CURRENT.md](docs/CURRENT.md)
- 项目记忆索引：[.agent/memory/MEMORY.md](.agent/memory/MEMORY.md)
- 变更记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)

<!-- 根据第 0 步的结果裁剪：没有 API 就删掉 api.md 那行，没有部署需求就删掉 deployment.md -->

<!-- 省略声明：被裁剪的信息在此声明"有意省略"，防止 Agent 以为遗漏而自行补全。
     示例：
     - 本文件未包含 API 约定（项目无 API 接口）。
     - 本文件未包含部署说明（项目无独立部署流程）。
     根据实际裁剪情况填写，全部保留时删除本段。 -->

## 项目记忆

<!-- 本节是硬约束——AGENTS.md 始终在 Agent 上下文中，因此关键记忆内联于此保证模型可见。
     详细记忆见 .agent/memory/MEMORY.md。小型项目删除本节。 -->

- **用户**：<!-- 称呼、关键偏好、技术栈 -->
- **项目上下文**：<!-- 当前活跃项目的一句话描述 -->
- **最近教训**：<!-- 最重要的 1-2 条 -->
- **详细记忆**：[.agent/memory/MEMORY.md](.agent/memory/MEMORY.md)

> 每次更新 `.agent/memory/` 后，同步维护本节摘要。MEMORY.md 的索引标记段（`<!-- memory-index:start/end -->`）由 `python scripts/maintain.py` 自动重建——agent 只负责记忆的沉淀与检索，不手工编辑标记段内容。

## 行为规则

### Compact 恢复（上下文压缩后强制执行）

若你的上下文中包含 "continued from a previous conversation"（compact 恢复信号），在继续任何实质性工作前：

1. 读取 `docs/CURRENT.md` — 确认当前任务状态
2. <!-- 非小型项目保留本行；小型项目删除本行 -->
   读取 `.agent/memory/MEMORY.md` — 恢复项目记忆与用户画像
3. 上述步骤完成前，**禁止执行写操作、禁止做出有副作用的判断**

> 本条是止损措施——compact 后 Agent 丢失大量上下文，必须先恢复关键状态再行动。当前依赖 Agent 遵守（软约束）；待框架支持 compact 事件 hook 后迁移为硬约束。

### 任务前记忆检索

除非任务非常简单明确，开始实质性工作前必须先检索记忆系统获取参考——git log / CHANGELOG / `.agent/memory/` 都是记忆系统的一部分：

1. `git log --oneline -15` 和/或 `python scripts/changelog.py recent` — 近期变更脉络
2. 读取 [.agent/memory/MEMORY.md](.agent/memory/MEMORY.md) — 过往经验、教训与用户画像<!-- 小型项目删除本行 -->
3. 命中相关记忆文件时按需深入阅读

唯一豁免：用户当次明确表示不需要。

### 硬约束（不可违反）
<!-- 候选项：只有目标仓库已有约束或用户确认时保留。下面的密钥、构建产物、hook 等通用规则不要无脑写入最终 AGENTS.md；保留时必须改成目标仓库的具体路径、命令或约束。 -->
- **密钥不入库**：API Key 只放环境变量文件（如 `.env`），不硬编码。
- **不碰构建产物**：<!-- 列出项目的构建产物路径，如 dist/、build/、data/、node_modules/ --> 属于生成物，除非任务明确要求，否则不要修改。
- **文件落位**：新增文件按用途归位到既有目录，不堆在仓库根；<!-- 填项目的目录约定，如 脚本→scripts/、可执行/调试工具→tools/、测试→tests/、文档→docs/，按目标仓库实际目录和生态调整 -->一次性/临时脚本用完即删或放仓库外，不提交；根目录只保留约定俗成的工程文件（manifest、配置、README、instruction 文件等）。
- **不绕过 hook**：项目启用了 `.githooks/pre-commit` 时，lint 失败先修复再提交，不要用 `--no-verify` 跳过。
- **完工必检**：任务完成后必须执行末尾的"完工检查清单"，不可跳过，不可先回复用户再补。
<!-- 根据项目补充其他硬约束，例如：
- **前后端同步**：修改后端 schema 后同步更新前端类型定义。
- **不修改生产数据库 schema**：schema 变更必须通过 migration。
-->

### 默认偏好（有充分理由可偏离）
<!-- 候选项：只有目标仓库已有约束或用户确认时保留。"先读后改"、"风格跟随"、语言命名等通用偏好，如果不能转化成仓库特异约束，应删除或压缩。 -->
- **先读后改**：修改任何文件前先读取，理解现有逻辑再动手。
- **风格跟随**：跟随已有代码风格，不引入新范式。
- **Occam**：如无必要，勿增实体；新增文件、字段、脚本、规则或流程前，先确认它解决的具体问题。
- **Bitter Lesson**：通用方法优于硬编码先验；优先复用模型能力、语义检索、结构化工具和默认流程，谨慎增加任务枚举、关键词规则和提前分类。
- **模式匹配与执行模式**：单会话能完成的小任务用直接执行模式；涉及跨模块、预计改动超过 5 个文件、或可能跨会话完成的任务，走**复杂任务闭环**。
- **复杂任务闭环（计划 → 审计 → 拍板 → 执行 → 验收）**：中型及以上项目，或涉及 3 个以上文件、跨模块、可能跨会话的任务，必须走闭环：
  1. **计划**：在 `docs/plans/active/` 落盘具体方案（问题清单、影响文件、验收标准）。
  2. **审计**：用 subagent 审计计划，修正漏洞和遗漏。
  3. **拍板**：向用户呈现计划，确认后再执行。
  4. **执行**：严格按计划逐项修改，不发散。
  5. **验收**：用 subagent 审计执行结果，确认与计划一致。

  **升级触发**：若当前会话已连续 2 轮以上反复修同一个问题，或执行完毕后仍出现 bug，agent 必须主动向用户提议："当前开发节奏可能存在失控风险，建议切换到计划驱动工作流，先写计划再执行。"
- **任务启动先读 CURRENT.md**：接到新任务时，先读取 `docs/CURRENT.md`。若存在未完成的上下文（任务状态非"无"），向用户确认是继续还是覆盖。
- **并行协作时**：把状态真相源放在计划文件，而不是塞进一个全局 CURRENT.md。
- **任务级选择模式**：项目可以有默认协作倾向，但每个任务开始前仍要按复杂度、风险和是否并行重新判断采用哪种模式。
- **验证尽量换视角**：高风险改动优先由新上下文或 reviewer 视角复查，不把"执行者自检"等同于"已验证"。
<!-- 根据项目补充具体的代码风格约定，例如：
- Python `snake_case`，4 空格缩进
- TypeScript/React `camelCase` 变量、`PascalCase` 组件
-->

### 多 Agent worktree 路由（可选机制）

<!-- 候选项：仅当项目确认多 Agent / 多窗口并行倾向、且已按 SKILL.md 第 6.5 步
     安装 scripts/worktree_task.py（及可选 reference-transaction hook）时保留；
     否则整节删除。 -->

- 普通 tracked 写任务默认先 `python scripts/worktree_task.py create` 获得独立 branch（`task/<id>`）与 linked worktree，在 worktree 内提交后 `integrate` 回主分支。纯查询、用户直接编辑、单文件小修补不创建 worktree。
- 四动作：`create` / `check <id>` / `integrate <id>` / `cleanup <id>`。失败保留 task 对象：`needs-rebase` 在 task worktree 内 rebase 主分支后重试；`head-drift` 复核后重试；响应丢失重试由 Git ancestry 判 `already-integrated`。
- 孤儿发现：`git worktree list --porcelain` 与 `git branch --list 'task/*'`；仅对可证明 clean 的对象执行 `cleanup`。

## 测试要求

<!-- 根据项目实际情况填写。示例：
- 有完整测试套件：从 CI / hook / task runner / manifest scripts 提取精确命令，如后端 `pytest tests/api/test_orders.py -v`，前端 `pnpm --filter web test`，改动后必须通过。
- 没有自动化测试：后端改动至少验证 `GET /health` 和受影响的接口；前端改动跑 `npm run lint` 并手动 smoke-test。
-->

## 安全与配置

<!-- 可选节。项目涉及密钥管理、认证流程、部署凭证、敏感数据时保留；否则删除本节。 -->
<!-- 示例：
- **密钥管理**：所有密钥通过 `.env` 文件注入，不硬编码。`.env` 已在 `.gitignore` 中排除。
- **认证流程**：JWT token 有效期 24h，刷新 token 有效期 7d。token 生成逻辑见 `src/auth/jwt.ts`。
- **敏感数据**：生产数据库禁止本地直连，必须通过跳板机或 VPN。
- **部署凭证**：CI/CD 使用 GitHub Secrets，不暴露在 workflow 日志中。
-->

## 提交规范

<!-- 候选项：只有目标仓库已有约束或用户确认时保留；否则删除本节。 -->
使用 Conventional Commit 风格：`feat:` / `fix:` / `chore:` 等。

**及时提交**：完成一个功能阶段后主动暂存源码文件并提交，避免 diff 膨胀导致上下文压力。排除二进制生成物。

**PR 要求**：
- 说明改了什么、为什么改
- 列出影响范围（哪些模块/接口）
- 有迁移步骤时必须写明
- 关联相关 issue（如有）

## 文档维护原则

**核心理念：只记代码里读不出来的东西。** 目录结构、模块职责、技术栈、函数签名等可从代码直接获取的内容不写入文档。文档只记设计原因、协作约束和不能从代码推导的信息。

1. **不重复**：同一信息只在最合适的位置出现一次。流程图已描述的逻辑不在职责表重复，职责表已列的模块不再单独建表。
2. **不展开实现细节**：CSS 断点、具体字段列表、SQL 建表语句等可从代码直接获取的内容，一句话概括 + 指向源文件即可。
3. **合并同类**：前后端模块统一到一张职责表，避免拆成多张小表增加行数。
4. **补充说明从简**：流程图下方的文字补充只写流程图中未体现的关键差异或设计决策，不复述流程步骤。
5. **可从代码/git 推导的不写**：文件路径、函数签名、参数默认值等会随代码变化的细节，优先让读者查看源码，文档只记"为什么这样设计"。

**`docs/` 的使用边界**

6. 新增设计决策写入 [docs/overview.md](docs/overview.md)；接口变更更新 [docs/api.md](docs/api.md)；部署或环境约束更新 [docs/deployment.md](docs/deployment.md)；环境陷阱写入 [docs/pitfalls.md](docs/pitfalls.md)。
7. 先更新对应 `docs/*.md`，再写 [docs/CHANGELOG.md](docs/CHANGELOG.md)。CHANGELOG 只记变更摘要，不重复架构文档正文。
8. 单个架构文档接近 300 行时按主题拆分，并在 [docs/STRUCTURE.md](docs/STRUCTURE.md) 里补索引，不在原文件里继续堆叠。
9. 需要走"复杂任务闭环"的任务，先在 `docs/plans/active/` 落盘计划，实施完成后移到 `docs/plans/completed/`。单会话小任务不必建计划。

**CHANGELOG 规则**

10. 日期节倒序排列，最新在前；同一天的多次修改合并到同一个日期节，用 `###` 区分主题。
11. 写入 [docs/CHANGELOG.md](docs/CHANGELOG.md) 前**不要读全文**；使用 `python scripts/changelog.py titles --limit 5` 查看标题树，`python scripts/changelog.py show --date YYYY-MM-DD` 或 `--match 关键词` 读取局部内容，`python scripts/changelog.py add --title "..." --body "..."` 追加条目。
12. 当前任务状态写入 [docs/CURRENT.md](docs/CURRENT.md)，不要写进 CHANGELOG。
13. 只写"改了什么、为什么改、有什么迁移影响"，不贴代码，不重复 `docs/` 中已经存在的设计说明。

**定期审计**

14. 每 ~20 次任务或每月，运行 `python scripts/maintain.py`（重建记忆索引 + 机械检查 + 记忆活性报告 + 近期脉络摘要）；无记忆系统的小型项目直接运行 `python scripts/audit.py check`。如发现 `[DEAD]` / `[DRIFT]` / `[UNDOC]` / `[ORPHAN]` / `[BROKEN]` 项，读取 [docs/audit-checklist.md](docs/audit-checklist.md) 按清单逐项裁决。审计完成后将结果写入 CHANGELOG。

### docs/ 文件的治理规则

> 以下规则定义 docs/ 下每个文件的存在条件、合并条件和创建/删除原则。这些是 Agent 必须遵守的硬约束。

**存在条件**：
- 每个 docs/ 文件的存在条件是它能回答一个 AGENTS.md 无法承载的"为什么"问题。
- 不存在条件则不创建。条件消散则合并或删除。
- 具体判断由 Agent 在任务上下文中决定，不预编码枚举条件。

**合并条件**（何时并入 AGENTS.md）：
- 当文件内容足够短，内联不会明显增加 AGENTS.md 的认知负担，且 AGENTS.md 行数未超过 200 行/400 词时，内联优于独立文件。
- 当文件的唯一读者是 Agent 且信息在每次对话中都应可见时，应内联。
- 批量合并前评估 AGENTS.md 是否会超出行/词上限，若会则保留并简化指针。

**创建原则**：
- 新增前必须说清它解决的具体问题（Occam）。
- 优先用 AGENTS.md 已有段落或现有 docs/ 文件容纳信息；仅在现有结构无法容纳时才新建。
- 不预编码创建条件的枚举规则（Bitter Lesson）。

**删除原则**：
- 内容已迁移到其他文件且无残留引用 → 直接删除。
- 内容过时且 git log 可追溯 → 删除，不保留弃用标注。
- 信息已自然融入 AGENTS.md → 删除，并在 AGENTS.md 指针段中移除对应行。

**自免声明**：本条治理规则不评估自身——治理规则的修订走正常的计划/审批流程，不通过自动化自应用触发删除/合并判定。

## 完工检查清单

文档是跨会话协作的唯一记忆。代码改了但文档没跟上，下一次对话会基于过时信息做决策，产生连锁错误。**每次编辑任务完成后，必须逐项走完以下清单，再向用户报告完成。**

- [ ] **验证**：改动涉及的功能是否仍能正常工作？前端改动至少在浏览器确认无白屏/控制台无报错；后端改动至少确认服务能启动。
- [ ] **复查视角**：如果这是高风险或跨模块任务，是否至少经过一次新的 reviewer 视角复查（新上下文窗口优先）？没有做到时，在计划或回复中明确说明。
- [ ] **架构文档（docs/）**：是否涉及架构变更（新模块、新接口、流程变化、新配置、端口/环境变化）？如是，更新 `docs/` 下对应文件。维护时遵循本文件中的"文档维护原则"。
- [ ] **CHANGELOG.md**：是否值得记录？如是，用 `python scripts/changelog.py add ...` 插入到当天日期节；需要查看历史时只用 `titles/show` 局部读取。
- [ ] **同步一致性**：本文件若被编辑，运行 `python scripts/agent_links.py check`；只有不一致时才用 `python scripts/agent_links.py repair` 修复。
- [ ] **跳过条件**：纯格式修改、注释修改、同一会话内已记录的变更，可跳过文档更新步骤（但验证步骤不可跳过）。
- [ ] **记忆自检**：本次对话是否产生值得沉淀的记忆（用户偏好、项目上下文、可复用教训）？如是，更新 `.agent/memory/` 对应文件并同步 AGENTS.md「项目记忆」内联摘要；MEMORY.md 索引段由 `python scripts/maintain.py` 维护，无需手改。<!-- 小型项目：标注"小型项目，无记忆目录" -->
