---
title: Skill 质量评估基线与测试用例
purpose: 定义 init-agent-docs skill 的三层验证框架、测试数据与评分标准，用于回归测试和持续迭代
---

## 评估哲学

Skill 的价值不仅在于"能跑"，更在于**相比无 Skill 的基线是否有显著增益**。因此评估必须包含：

1. **功能正确性**（L1）：文件创建、脚本运行、同步一致性
2. **触发精准度**（L2）：真实用户话术下的命中率与误触率
3. **质量增益**（L3）：有 Skill vs 无 Skill 的产出质量对比

---

## 测试项目矩阵

准备 3 组典型项目作为 test bed：

| 项目代号 | 规模 | 特征 | 初始化预期选项 |
|---------|------|------|-------------|
| `eval-small` | 小型 | Python 单文件脚本（< 5 个核心文件），无现有文档 | 小型：AGENTS.md + docs/CHANGELOG.md + docs/CURRENT.md |
| `eval-medium` | 中型 | Node.js 全栈应用（15–25 个文件），有 README 和 API 文档 | 中型：全套 docs/ + docs/STRUCTURE.md + plans/ |
| `eval-large` | 大型 | 多模块微服务（> 30 个文件），多语言混合，已有 DESIGN.md | 大型：中型全套 + 模块级拆分提示 + 迁移旧文档 |

**新增事实源冲突夹具**：

1. `eval-medium`：README 写旧命令（例如 `npm test`），但 `package.json`、lockfile 和 CI 写真实命令（例如 `pnpm test --filter web`）。预期产物遵守**可执行事实源优先**，`AGENTS.md` 记录真实命令，不复制 README 旧命令。
2. `eval-large`：包含 workspace / monorepo 配置、root 命令和 package-level 命令。预期产物能说明单包验证方式、workspace 边界和必要命令顺序，而不是只写泛化的"运行测试"。
3. `eval-medium` 或 `eval-large`：加入已有 `CLAUDE.md`、`.cursor/rules/project.mdc`、`.github/copilot-instructions.md` 或 repo-local `opencode.json`。预期产物完成**已有 instruction 文件整合**，保留其中已验证的硬约束、Agent 行为限制和禁止事项，不盲目覆盖。

**准备步骤**：
1. 在临时目录下创建 3 个最小可运行的项目骨架（不必能真正运行，但目录结构和关键文件要真实）
2. 给每个项目写一段 100 字左右的"项目画像"（技术栈、硬约束、协作模式），作为第 0 步的模拟输入
3. 用 Git 初始化仓库，确保能测试 pre-commit hook

---

## L1：执行验证清单

对每组 test bed 执行 skill，完成后逐项检查：

### 通用项（所有规模）

- [ ] `AGENTS.md` 已创建且非空
- [ ] `CLAUDE.md` / `GEMINI.md` 与 `AGENTS.md` 同步一致：`python scripts/agent_links.py check` 返回 0
- [ ] `CHANGELOG.md` 可由 `python scripts/changelog.py titles --limit 3` 输出至少一条标题
- [ ] `docs/CURRENT.md` 已创建
- [ ] `AGENTS.md` 中所有链接指向真实存在的文件（小型项目特别注意死链）
- [ ] `AGENTS.md` 行数 ≤ 200（小型项目 ≤ 150 更佳）
- [ ] 未残留未删除的模板指导注释（`<!-- ... -->` 或 `[方括号]` 占位符）
- [ ] 可执行事实源优先：当 README 写旧命令而 CI / manifest / hook 写真实命令时，`AGENTS.md` 采用真实命令
- [ ] 已有 instruction 文件整合：旧 `AGENTS.md` / `CLAUDE.md` / Cursor / Copilot / OpenCode 指令中的硬约束已被读取、去重并保留
- [ ] 用户提问克制：仓库事实源已经能回答的命令、入口、测试方式、工具链顺序，不应再询问用户

### 中型 / 大型额外项

- [ ] `docs/STRUCTURE.md` 存在且索引表与 `docs/` 文件一一对应
- [ ] `docs/plans/active/` 和 `docs/plans/completed/` 目录存在
- [ ] `docs/overview.md` 已创建且包含至少一句设计决策说明
- [ ] `docs/deployment.md` 已创建
- [ ] 出生档案（`docs/plans/completed/initialization.md` 或 `docs/initialization.md`）已写入

### 大型额外项

- [ ] 迁移的旧文档顶部有"已迁移"标注，未直接删除
- [ ] AGENTS.md 或 overview.md 中包含模块级拆分的提示语

### 脚本验证

- [ ] `scripts/changelog.py titles` 正常输出
- [ ] `scripts/changelog.py add --title "test" --body "test body"` 成功追加且格式正确
- [ ] `scripts/agent_links.py check` 通过
- [ ] `scripts/agent_links.py repair` 能修复人为断链
- [ ] pre-commit hook 能阻止不一致提交（手动破坏 CLAUDE.md 后尝试提交，应被拒绝）

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
| 硬约束无工具支撑 | 执行步骤第 6 步 | 强化 pre-commit hook 的必做要求，增加 CI 矩阵 |
| 渐进披露不合理 | SKILL.md 设计哲学第 2 条 | 调整 AGENTS.md 行数上限建议，或增加 docs/STRUCTURE.md 的强制要求 |
| 维护机制缺失 | 执行步骤第 5 步 | 强化"出生档案"和 CHANGELOG 脚本的必做要求 |
| 事实源裁决错误 | SKILL.md 第 0 / 第 3 步 | 强化可执行事实源优先规则，补充 README 写旧命令的夹具 |
| 旧指令文件丢失 | SKILL.md 第 1 步 | 扩展已有 instruction 文件整合范围，要求读取 Cursor / Copilot / OpenCode 指令 |

---

## 回归测试执行流程

1. **准备 test bed**：确认 3 组项目骨架可用
2. **运行 L1**：对每组执行 skill，过静态自检清单
3. **运行 L2**：用 12 组话术测试触发（6 组应触发 + 6 组不应触发）
4. **运行 L3**：选择 1 组 test bed（建议 `eval-medium`）做 baseline 对比盲评
5. **记录结果**：填入下表

| 版本 / commit | L1 通过 | 命中率 | 误触率 | 无 Skill 均分 | 有 Skill 均分 | 主要问题 |
|--------------|---------|--------|--------|--------------|--------------|---------|
| 当前 main | | | | | | |

6. **迭代**：根据失败项和评分差，修改 SKILL.md / 模板 / 脚本，再跑一轮

---

## 自动化可能性

- **L1**：可脚本化（检查文件存在、行数、链接有效性、脚本返回值）。建议作为 CI 步骤在每次提交前运行
- **L2**：目前需人工在 Claude Code 中测试，但可用批量会话脚本辅助记录结果
- **L3**：评分部分依赖主观判断，但可用"另一个 Agent 盲评"部分自动化

**短期目标**：先完成一次全手动 eval，建立基线数据；再逐步将 L1 和 L3 中的机械检查项脚本化。
