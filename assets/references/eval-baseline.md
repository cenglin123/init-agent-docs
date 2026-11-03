---
title: Skill 质量评估基线与测试用例
purpose: 定义 init-agent-docs skill 的三层验证框架、测试数据与评分标准，用于回归测试和持续迭代
---

## 评估哲学

Skill 的价值不仅在于"能跑"，更在于**相比无 Skill 的基线是否有显著增益**。评估分三层：

1. **静态合同**（L1）：文件创建、脚本运行、机械检查通过、profile 矩阵验证
2. **合成树**（L1.5）：在合成目录结构上运行脚本，验证无 Git 时行为正确、无死链、无内部 assets/references/ 链接
3. **行为评估**（L2/L3）：Agent 实际执行 skill 的产出质量（advisory，非确定性门槛）

---

## 方法版本

当前方法标识：`context-bounded-l1-v2`。本节之后定义当前验收方法；回归表保留各次实际执行范围与结果，历史记分不按新方法追写或改分。新记录注明采用的方法标识。

## 测试项目矩阵

准备四个 profile 项目作为 test bed，覆盖四个 Profile 轴（Git/no-Git × Small/Medium）：

| 项目代号 | 规模 | 特征 | 初始化预期选项 | Profile |
|---------|------|------|-------------|---------|
| `eval-small` | 小型 | Python 单文件脚本（< 5 个核心文件），无现有文档 | Small 必备集合（见下表后清单） | Small + Git |
| `eval-small-nogit` | 小型 | 同 eval-small，但不在 Git 仓库中 | Small 必备集合；无 Git 指引 | Small + no-Git |
| `eval-medium` | 中型 | Node.js 全栈应用（15–25 个文件），有 README 和 API 文档 | Medium 必备集合，含治理专题/记忆/维护器 | Medium + Git |
| `eval-medium-nogit` | 中型 | 同 eval-medium，但不在 Git 仓库中 | Medium 必备集合；无 Git 指引，活性统计回退到 mtime | Medium + no-Git |

必备集合（所有项须逐一核对，不能把文档表中的简称当作完整清单）：

- Small：AGENTS.md、README.md、docs/CURRENT.md、docs/CHANGELOG.md、docs/audit-checklist.md、docs/initialization.md，以及 scripts/changelog.py、scripts/audit.py、scripts/check_all.py。
- Medium/Large：通用入口/README/CURRENT/CHANGELOG/audit-checklist 与三个脚本，加 docs/STRUCTURE.md、overview.md、deployment.md、governance.md、plans/{active,completed}/、problems/bugfix/_template.md、.agents/memory/{MEMORY.md,user/role.md}、scripts/maintain.py；初始化记录验收前为 plans/active/initialization.md，通过后为 plans/completed/initialization.md。可选专题按实际生成核对。KB 项目将脚本/记忆目录及维护器名按入口路径契约投影。

**新增事实源冲突夹具**：

1. `eval-medium`：README 写旧命令（例如 `npm test`），但 `package.json`、lockfile 和 CI 写真实命令（例如 `pnpm test --filter web`）。预期产物遵守**可执行事实源优先**，`AGENTS.md` 记录真实命令，不复制 README 旧命令。
2. `eval-large`：包含 workspace / monorepo 配置、root 命令和 package-level 命令。预期产物能说明单包验证方式、workspace 边界和必要命令顺序，而不是只写泛化的"运行测试"。
3. `eval-medium` 或 `eval-large`：加入已有 `CLAUDE.md`、`.cursor/rules/project.mdc`、`.github/copilot-instructions.md` 或 repo-local `opencode.json`。预期产物完成**已有 instruction 文件整合**，保留其中已验证的硬约束、Agent 行为限制和禁止事项，不盲目覆盖。

**准备步骤**：
1. 在临时目录下创建四个 profile 的项目骨架（不必能真正运行，但目录结构和关键文件要真实）
2. 给每个项目写一段 100 字左右的"项目画像"（技术栈、硬约束、协作模式），作为调查阶段的模拟输入
3. 仅 Git profile 使用已有 Git 配置或建立隔离测试仓库；no-Git 不运行 Git。

---

## L1：执行验证清单

对每组 test bed 执行 skill，完成后逐项检查：

### 通用项（所有规模）

- [ ] `AGENTS.md` 已创建且非空
- [ ] `AGENTS.md` 是唯一入口：无 `CLAUDE.md` / `GEMINI.md` 残留副本（迁移场景已整合删除）
- [ ] `CHANGELOG.md` 可由 `python scripts/changelog.py titles --limit 3` 输出至少一条标题
- [ ] `docs/CURRENT.md`、根 README.md 与 docs/audit-checklist.md 已创建且非空
- [ ] scripts/changelog.py、scripts/audit.py、scripts/check_all.py 已安装且实际命令可运行（KB 按实际布局）
- [ ] 所有 profile 的出生档案已写入正确位置：Small 在 docs/initialization.md 原地保留；中大型验收前 active、验收后 completed。进行中状态不能冒充独立验收完成
- [ ] 新出生档案的 size/repository_mode/status 使用初始化参考规定的枚举；来源组件哈希与可回取的语义生成基线正文一致
- [ ] `AGENTS.md` 中所有链接指向真实存在的文件（小型项目特别注意死链）
- [ ] `AGENTS.md` 行数 ≤ 250（小型项目 ≤ 150 更佳）
- [ ] 未残留未删除的模板指导注释（`<!-- ... -->` 或 `[方括号]` 占位符）
- [ ] 可执行事实源优先：当 README 写旧命令而 CI / manifest / hook 写真实命令时，`AGENTS.md` 采用真实命令
- [ ] 已有 instruction 文件整合：旧 `AGENTS.md` / `CLAUDE.md` / Cursor / Copilot / OpenCode 指令中的硬约束已被读取、去重并保留
- [ ] 用户提问克制：仓库事实源已经能回答的命令、入口、测试方式、工具链顺序，不应再询问用户

- [ ] 初始化起始有可恢复状态，CURRENT 仅指入口；来源含版本状态与实际组件哈希/生成基线；独立验收后才置 done
- [ ] Small 最小治理从通用合同投影；无不存在资产的纯文本指引；治理候选与出生档案分离

### 中型 / 大型额外项

- [ ] `docs/STRUCTURE.md` 存在且索引表与 `docs/` 文件一一对应
- [ ] `docs/plans/active/` 和 `docs/plans/completed/` 目录存在
- [ ] governance.md 从 AGENTS 与 STRUCTURE 双导航可达
- [ ] `docs/overview.md` 已创建且包含至少一句设计决策说明
- [ ] `docs/deployment.md` 已创建

### 大型额外项

- [ ] 迁移后的约束有明确去向，已迁空旧文档直接删除，正文不留弃用标注
- [ ] AGENTS.md 或 overview.md 中包含模块级拆分的提示语

### Small 额外项

- [ ] Small 必备集合逐项存在；不建 STRUCTURE、plans、memory、maintain 或 governance 专题，审计全文没有这些不存在资产的操作指引
- [ ] README、审计清单、CURRENT 与初始化出生档案相互指向真实位置；候选记录与普通任务不覆盖出生档案

### 脚本验证

- [ ] `scripts/changelog.py titles` 正常输出，入口保留 titles/show/add/recent 局部操作与不读全文约束
- [ ] 所有 profile 运行 audit.py check、check_all.py --quiet（Small 加 --small）；中大型额外运行 audit.py memory、maintain.py --check，KB 按实际布局替换
- [ ] 治理修改的独立复查及冻结基线盲评标定合同在生成入口可发现；同基线 ≥3 独立视角豁免与结论记录口径没有因改写而丢失
- [ ] `scripts/changelog.py add --title "test" --body "test body"` 成功追加且格式正确
- [ ] 迁移场景：旧入口副本（`CLAUDE.md` / `GEMINI.md` 等）内容已并入 AGENTS.md 且副本已删除
- [ ] 已安装 pre-commit hook 时，人为破坏记忆结构（移走 MEMORY.md）后提交应被拒绝

---

## L2：触发测试

**测试方法**：在 Claude Code 中输入以下话术，记录 skill 是否被正确触发。每组话术测试 3 次（不同会话，避免缓存干扰）。

### 应触发（命中率测试）

| 话术组 | 示例表达 |
|-------|---------|
| 直接功能型 | "初始化项目的 AI 协作文档"、"给仓库搭一套 CLAUDE.md"、"建立 agent-first 文档体系" |
| 场景驱动型 | "帮我给这个项目写一份 Agent 能看懂的说明"、"整理一下现有文档，让 AI 能更好地协作" |
| 迁移型 | "把 README 和 ARCHITECTURE 整理成 Agent 友好格式"、"迁移现有文档到新的 AI 协作规范" |
| 英文型 | "set up agent collaboration docs"、"initialize CLAUDE.md for this repo"、"scaffold agent-first documentation" |

**命中率标准**：每组至少 2/3 触发。整体命中率 ≥ 75%。

### 不应触发（误触率测试）

| 话术组 | 示例表达 |
|-------|---------|
| 通用文档 | "写一份项目文档"、"更新 README"、"补充 API 文档" |
| 代码任务 | "修复这个 bug"、"重构认证模块"、"添加单元测试" |
| 其他 Skill | "生成一张封面图"、"写短视频文案"、"整理学习笔记" |

**误触率标准**：每组 0/3 触发。整体误触率 = 0%。

**触发失败时的修复映射**：

| 症状 | 修复位置 | 修复方法 |
|------|---------|---------|
| 应触发的话术未触发 | SKILL.md frontmatter `description` | 补充同义词或口语化表达 |
| 英文话术不触发 | `description` | 添加英文关键词或触发示例 |
| 通用文档请求误触发 | `description` | 在 description 中明确限定"初始化/搭建/迁移"动作，排除"单纯写文档" |

---

## L3：质量评分与 Baseline 对比

### 评分维度（0–10 分）

对每组 test bed，分别执行**无 Skill 自由发挥**和**有 Skill 按流程执行**，然后对产出的 `AGENTS.md` 打分：

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| **信息密度** | 25% | 是否只包含"代码读不出的东西"？有没有混入目录结构、函数签名等可推导信息？ |
| **导航清晰度** | 25% | 新 Agent 只看 AGENTS.md 能否在 30 秒内知道"这个项目做什么、我不能改什么、任务完成要做什么"？ |
| **硬约束可执行性** | 20% | 硬约束是否有配套工具（hook、脚本）强制执行？还是仅靠文字提醒？ |
| **渐进披露合理性** | 15% | 信息分层是否符合"AGENTS.md 指针 → docs/ 深度 → 脚本工具"的结构？有没有该下沉却没下沉的内容？ |
| **维护可持续性** | 15% | 文档体系是否预留了"只增不删会腐烂"的应对机制？CHANGELOG 脚本、计划文件状态机是否到位？ |

**额外扣分项**：如果 README、旧文档或模板默认文案与 CI / hook / manifest scripts 冲突，而产物没有采用可执行来源，"信息密度"和"硬约束可执行性"都应扣分；如果已有 instruction 文件被未读覆盖，"导航清晰度"和"维护可持续性"都应扣分。

### 评分等级

| 分数 | 含义 |
|------|------|
| 0–2 | 完全不可用，方向错误或关键文件缺失 |
| 3–4 | 勉强能用，但存在明显结构缺陷或死链 |
| 5–6 | 基本达标，Agent 能工作，但有优化空间 |
| 7–8 | 质量稳定，结构清晰，可直接用于生产 |
| 9–10 | 示范级输出，可作为其他项目的模板 |

**最低标准**：每个 test bed 的主要维度（信息密度 + 导航清晰度）≥ 5 分，总分 ≥ 6 分。

### Baseline 对比方法

1. **无 Skill 基线**：在全新会话中，不给任何 skill，直接对 test bed 说"请为这个项目创建一套 AI Agent 协作文档，包含 AGENTS.md 和必要的配套文件"。记录 Agent 自由发挥的结果。
2. **有 Skill 测试**：在全新会话中，让 Agent 按本 skill 执行。
3. **盲评**：让第三方（或另一个 Agent 会话）只看两份 AGENTS.md，分别按上述维度打分，不知道哪份来自 Skill。

**增益判定**：
- 无 Skill 7 分，有 Skill 7 分 → **无显著增益**，Skill 只是标准化了流程，未提升质量上限
- 无 Skill 4 分，有 Skill 8 分 → **显著增益**，Skill 把经验固化进去了
- 无 Skill 8 分，有 Skill 6 分 → **负增益**，Skill 反而拖累了，需紧急修复

### 质量问题的修复映射

| 症状 | 修复位置 | 修复方法 |
|------|---------|---------|
| 信息密度低（混入可推导信息） | AGENTS.md 模板 | 收紧模板中的"不要放什么"清单，增加反模式提示 |
| 导航不清晰 | AGENTS.md 模板"信息导航"段 | 增加具体示例，或调整指针顺序 |
| 硬约束无工具支撑 | optional-integrations.md 质量 hooks | 为硬约束补配 hook / CI / 检查脚本，使其可机械验证 |
| 渐进披露不合理 | design-principles.md 地图与事实源 | 调整 AGENTS.md 行数上限建议，或增加 docs/STRUCTURE.md 的强制要求 |
| 维护机制缺失 | initialization.md 验收与交付 | 强化"出生档案"和 CHANGELOG 脚本的必做要求 |
| 事实源裁决错误 | initialization.md 调查/迁移 | 强化可执行事实源优先规则，补充 README 写旧命令的夹具 |
| 旧指令文件丢失 | initialization.md 最小入口与迁移 | 扩展已有 instruction 文件整合范围，要求读取 Cursor / Copilot / OpenCode 指令 |

---

## 回归测试执行流程

1. **准备 test bed**：确认四个 profile 项目骨架可用
2. **运行 L1**：对每组执行 skill，过静态自检清单
3. **运行 L2**：用 12 组话术测试触发（6 组应触发 + 6 组不应触发）
4. **运行 L3**：选择 1 组 test bed（建议 `eval-medium`）做 baseline 对比盲评
5. **记录结果**：填入下表

| 版本 / commit（完整 40 位 SHA） | 日期 | L1 通过 | 命中率 | 误触率 | 无 Skill 均分 | 有 Skill 均分 | 护栏 | 记分来源 | 主要问题 |
|--------------|------|---------|--------|--------|--------------|--------------|------|---------|---------|
| `4dc052d757c66d325af88648152c9dc7606724d5` | 2026-10-27 | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | — | converge 评议 20261027（3R 评议+盲审） | 基线行；正式记分待首轮全量 eval |
| `9d2903e45a5217b4d0a5751a57ac41577b6e8592` | 2026-11-01 | L1 partial: scope=step9-static（模板债务段存在/段序在审计记录之前/无残留占位符，AGENTS 完工必检含债务指针；2 结构断言通过） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | — | 标准 converge 1R（ses_e683d8b0，22 项发现修正 21） | 结构吸纳（债务登记）；skipped=4/4 test bed 执行维度、L2/L3 全跳，噪音率 100%，如实计入 |
| `82606afa5db97c53c2fb9886d38656eecaef02cb` | 2026-11-01 | L1 partial: scope=philosophy5-6-style（标定/局部核对/三问句/边界条款 + AGENTS 完工必检自包含标定契约 + audit-checklist 触发段完整程序；22 静态断言通过） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | 未跑（基线待建） | — | ultraverge 3R×2 + R3 收敛确认（P1 5→4→2 单调收敛） | 哲学段吸纳（评审标定 + 执行不符局部核对）；skipped=4/4 test bed 执行维度、L2/L3 全跳，噪音率 100%，如实计入 |
| 工作区基于 `006148098bede51adb42b43714cebc684e0f9c91`，dirty；组件哈希见本次外置 instruction-metrics | 2026-11-02 | L1 partial: scope=入口路由、四profile模板投影、治理单源/双导航、恢复/来源合同；L1.5=SmallGit与MediumNoGit合成实物全部机械命令通过 | 未跑 | 未跑 | 未跑 | 未跑 | 尚无因果收益证据 | 默认pytest 124 passed（131.92s）；路由/脚本相关22 passed；外置synthetic-results保留初次投影器误删标记失败及修复 | L1独立Agent实物4/4未由本执行者验收，pilot由维护者另派；L2/L3未跑；此行不冒充真实Agent执行或旧新A/B |
| 本地未提交候选；`006148098bede51adb42b43714cebc684e0f9c91` 仅为 HEAD 基线，dirty；实际组件见外置 fix-round1-metrics | 2026-11-03 | 方法 context-bounded-l1-v2；L1 partial: scope=四profile入口/KB/生成保真与必备集合合同、size/记忆实质失败回归、嵌套noGit能力边界；L1.5=SmallGit/MediumNoGit最终合成树相同命令全部通过 | 未跑 | 未跑 | 未跑 | 未跑 | 独立发现驱动定点修复，尚无因果收益证据 | 默认pytest 150 passed（133.43s）；脚本针对67 passed，维护/指导33 passed；git diff --check通过 | 真实SmallNoGit/MediumGit/Large恢复pilot及最终独立验收由维护者另记；本行不冒充Agent pilot，初轮失败/记分保留；L2/L3未跑 |
| 本地未提交中间候选；HEAD `006148098bede51adb42b43714cebc684e0f9c91` 仅为基线 | 2026-11-03 | 方法 context-bounded-l1-v2；机械全量曾177 passed，但fresh原生审查发现quoted status跨检查不一致和普通MD读取异常；后续候选1 failed/184 passed又暴露读错误文案耦合，均未放行 | 未跑 | 未跑 | 未跑 | 未跑 | 失败证据保留，不以机械通过代替独立验收 | release-native/release-blind原报告及冻结快照；外置fix-round2-full-test-failure.json | 修复按原合同进行；不是新旧A/B，不抹去失败，不改变通过标准 |
| 本地未提交最终候选；HEAD `006148098bede51adb42b43714cebc684e0f9c91` 仅为基线，dirty；实际字节见外置release-candidate-metrics | 2026-11-03 | 方法 context-bounded-l1-v2；L1 partial: scope=年龄/状态退出语义、R1必填字段、出生档案兼容/冲突、UTF8结构化诊断、模板profile/导航与插件授权边界；L1.5=最终SmallGit/MediumNoGit合成实物原命令通过 | 未跑 | 未跑 | 未跑 | 未跑 | 保留中间失败；无因果收益结论 | 默认pytest185 passed（121.32s）；audit/check_all定向90 passed；git diff --check通过；release-synthetic保留脚本哈希及实际UTF8可选片段投影证据 | 真实pilot与两条fresh原生独立复核由主协调者另记；本行不冒充真实Agent pilot，L2/L3未跑 |
| 本地未提交185通过候选，实际源版本见该轮冻结manifest；HEAD `006148098bede51adb42b43714cebc684e0f9c91` 仅为基线 | 2026-11-03 | 方法 context-bounded-l1-v2；185机械回归通过后，独立盲评仍发现ledger与manifest两处读取边界遗漏，未放行 | 未跑 | 未跑 | 未跑 | 未跑 | 185通过不能代替独立验收 | release-blind原报告追加证据与旧冻结快照保留 | 沿用通过标准补两IO边界和预期读错误聚合保护，不吞逻辑异常 |
| 本地未提交待发布候选，dirty；HEAD `006148098bede51adb42b43714cebc684e0f9c91` 仅为基线，字节见外置release-candidate-final-metrics | 2026-11-03 | 方法 context-bounded-l1-v2；L1 partial: scope=前述四profile合同与A-F定点、quoted状态全caller一致、MD/ledger/manifest结构化读取失败和聚合继续；L1.5=release-synthetic-final两合成树原命令通过 | 未跑 | 未跑 | 未跑 | 未跑 | 既往失败证据均保留；无因果收益结论 | 默认pytest186 passed（125.44s）；test_audit79 passed；typed guard探针通过；git diff --check通过 | L1真实Agent执行与最终独立验收由主协调者另记；L2/L3全未跑，非旧新A/B或已部署证明 |
| 本地未提交待发布候选；HEAD `006148098bede51adb42b43714cebc684e0f9c91` 仅为现场基线，dirty=true；实际资产由冻结 publish manifest `7979FBDD3213F208D3490400631E5764C998E846AFC9A0FC12094FED72FC2E65` 字节标识 | 2026-11-03 | context-bounded-l1-v2；L1 partial：真实 Agent pilots 为 SmallNoGit、MediumGit；Large 为 fresh-context 接续；L1.5 合成树为 SmallGit、MediumNoGit；覆盖四 profile、KB 与保护文件 | 未跑 | 未跑 | 未跑 | 未跑 | CLI/ZIP 机械核对不证明质量或因果收益 | 默认 pytest 186 passed（125.44s）；Small 业务断言 exit 0；Medium `npm.cmd test` 13 项、Large `npm.cmd test` 35 项通过；外置 `acceptance/mechanical-release/completed-report.json` 独立机械核对通过 | 既有语义验收范围见外置 release-native/final-native 报告；本次只补机械核对；L2/L3 未跑，无旧新 A/B 或因果结论；GitHub push 待主协调，宿主部署未执行 |

6. **迭代**：根据失败项和评分差，修改 入口 / 参考 / 模板 / 脚本，再跑一轮

记分说明：

- 允许**范围化记分**（如 `L1 partial: scope=medium-git`）：scope 必须枚举实际触达的 test bed 维度，被跳过（skipped）的维度计入噪音率——不得用最小化的 scope 声明规避记分义务。
- `eval: skipped` 的比率作为噪音指标随记分行观测（L2 误触率之外的误报率腿）。
- 允许**批量补记**：一次会话补记多条历史改动时逐行登记，每行注明各自的记分来源。

---

## 护栏指标

护栏是回归表「护栏」列的信号来源，全部为**体系外信号**——eval 清单本身测不到的部分：

- **定义**：任务返工率、用户修正次数、同一问题重复出现次数等。
- **采集**：会话复盘与用户反馈，人工填写，无机械来源、无触发器。
- **Goodhart 说明**：护栏只作对冲信号，**不作优化目标**——为让护栏数字变好而做的调整违背其本意。
- **稀疏性**：允许稀疏、宁缺毋滥——仅在复盘确有信号时填写，空缺不是失职，也不为消警而凑数。

---

## 自动化可能性

- **L1**：可脚本化（检查文件存在、行数、链接有效性、脚本返回值）。建议作为 CI 步骤在每次提交前运行
- **R2（audit.py 的行为面记分强制）是过渡机制**：在 fixture 重放 runner 落地前，以「最近一次触碰回归表之后的行为面改动 commit 数」强制记分义务；runner 使记分连续化后，该机制退役
- **L2**：目前需人工在 Claude Code 中测试，但可用批量会话脚本辅助记录结果
- **L3**：评分部分依赖主观判断，但可用"另一个 Agent 盲评"部分自动化

**短期目标**：先完成一次全手动 eval，建立基线数据；再逐步将 L1 和 L3 中的机械检查项脚本化。
