---
name: init-agent-docs
description: >
  Initialize or migrate an agent-first doc system for AI collaboration.
  Creates synchronized AGENTS.md/CLAUDE.md/GEMINI.md, STRUCTURE.md, docs/ hierarchy
  with progressive disclosure, plan-as-handoff, and scripted CHANGELOG.
  Triggers when: setting up agent docs, scaffolding CLAUDE.md, building AI collaboration
  guidelines, migrating README/ARCHITECTURE to agent-friendly format.
  User phrases: "帮我初始化项目的 AI 协作文档", "给仓库搭一套 Agent 文档体系",
  "把现有文档整理成 AI 能协作的格式", "set up CLAUDE.md", "initialize agent-first docs".
---

# Init Agent Docs

为项目创建面向 AI Agent 的文档体系。核心理念来自 OpenAI Codex 团队的工程实践：**仓库即知识系统的唯一事实源，Agent 看不到的等于不存在。**

本 skill 仅用于初始化，不会驻留在 Agent 上下文中，因此不必节省篇幅。下面会详细解释每个设计决策的"为什么"，确保执行本 skill 的 Agent 充分理解意图，而不是机械地复制模板。

**本 skill 的模板和脚本存放在 [assets/](assets/) 下**；执行步骤里会告诉你什么时候 `Read` 哪个文件、`Write` 到目标项目的哪个路径。维护说明见 [README.md](README.md)。

**路径约定**：本 SKILL.md 中出现的 `assets/...` 路径一律相对**本 skill 根目录**（即本文件所在目录）；目标项目内的路径一律以"项目根"为基准（如 `scripts/changelog.py`、`docs/CURRENT.md`、`.githooks/pre-commit`）。当你在指令中看到这两类路径并存时，请按这个约定区分。

---

## 设计哲学

### 1. AGENTS.md 是目录，不是百科全书

> "Give Agents a map, not a 1,000-page instruction manual."

AGENTS.md（及其同步副本 CLAUDE.md、GEMINI.md）是 Agent 上下文中**始终驻留**的文件。这意味着它的每一行都在消耗 Agent 的注意力预算。一个 500 行的 AGENTS.md 会挤占任务描述、代码和文档的空间，导致 Agent "什么都看到了但什么都没注意"。

**AGENTS.md 的职责边界：**

| 应该放的 | 不应该放的 |
|---------|----------|
| 硬约束（不可违反的规则） | 模块职责、函数签名 |
| 默认偏好（可偏离的约定） | 目录结构描述 |
| 信息导航（指向 docs/ 的指针） | API 端点列表 |
| 完工检查清单 | 部署步骤详情 |
| 文档维护规则 | 设计决策的详细论述 |

**为什么需要三个文件名？** 不同 Agent 框架加载不同入口：Claude Code 加载 CLAUDE.md，Codex 加载 AGENTS.md，Gemini CLI 加载 GEMINI.md。通过脚本同步（copy 模式默认），让三个文件始终承载同一份内容，编辑 AGENTS.md 后运行 repair 即可同步到其他两个，避免内容漂移。

**建议控制在 200 行以内。** 如果超过了，说明有些内容应该下沉到 docs/ 中，AGENTS.md 只留指针。完工检查清单和 CHANGELOG 规则留在 AGENTS.md 里是有意为之——它们是最高频被违反的硬约束，下沉到按需读取的 docs/ 反而会被遗漏。

### 2. 渐进式披露（Progressive Disclosure）

Agent 从一个小而稳定的入口出发，按需深入查阅。这和给新员工入职一样——先给地图，再让他自己去探索，而不是第一天就塞一本 500 页的手册。

信息分层结构：

```
AGENTS.md          → 行为规则 + 导航指针（始终在上下文，~200 行）
STRUCTURE.md       → 文档总索引（一张导航表，Agent 需要时读取）
docs/*.md          → 各专题深度文档（Agent 按需读取特定文件）
docs/plans/        → 执行计划（Agent 接到复杂任务时读取）
CHANGELOG.md       → 变更记录（Agent 需要了解近期改动时读取）
```

**关键点：** 除了 AGENTS.md 始终在上下文中，其他文件都是 Agent 主动去读的。所以 AGENTS.md 必须告诉 Agent "什么信息在哪里"，这样它才知道该去哪找。

### 3. 只记代码里读不出来的东西

这是文档维护最重要的原则。违反它会导致两个问题：
- **信息腐烂**：文档说"函数 foo 接受 3 个参数"，代码改成了 4 个，文档没更新，Agent 基于过时信息决策。
- **上下文浪费**：Agent 读了一大段文档，结果这些信息从代码里就能看到，白白消耗了注意力预算。

**应该记录的：**
- 设计原因（"为什么用 SQLite 而不是 PostgreSQL"——代码只能看到用了 SQLite，看不到为什么）
- 协作约束（"前后端 schema 变更必须同步"——这是团队约定，代码里看不出来）
- 环境陷阱（"Windows 上 FAISS 安装需要 VS Build Tools"——这是踩坑经验）
- 外部系统的对接约定（"部署服务器的 /data 目录是持久化挂载"——这是基础设施信息）

**不应该记录的：**
- 目录结构（`ls` 一下就知道了）
- 模块职责（读代码和注释就知道了）
- 函数签名和参数默认值（IDE 和代码里都能看到）
- Git 历史和谁改了什么（`git log` / `git blame`）
- 技术栈列表（`package.json` / `requirements.txt` 就是事实源）

### 4. 计划是一等公民——跨上下文窗口与协作窗口的交接协议

复杂任务在开始前落一份计划到 `docs/plans/active/`，完成后移到 `docs/plans/completed/`。

**为什么计划如此重要？** Agent 的上下文窗口是有限的，且没有长期记忆。一个复杂任务不可能稳定地在一个上下文窗口里做完；多 Agent 或多窗口协作的任务也不能只靠口头上下文维持。

**计划文件本身就是交接协议**——它连接不同的上下文窗口和协作角色，让"失忆"的 Agent（新窗口）或从未参与前文的新 Agent 能够快速理解：
- 整体目标是什么
- 哪些阶段已完成、当前该做什么
- 前面的阶段留下了什么（改了哪些文件、有什么遗留问题）

详见 `assets/references/workflow-patterns.md`。

### 5. 验证应被视为独立视角，而不只是执行者自检

同一个 Agent 在同一个上下文窗口里做完实现，再立刻说"我已经验证过了"，天然带有确认偏误。它刚写完代码，最容易忽略自己埋下的问题。

因此文档体系里应显式给"验证"留位置：

- **高风险 / 跨模块改动**：必须由独立视角复查（新上下文窗口、subagent 或人类 reviewer），不接受执行者自检。
- **中等风险**：建议换视角，至少在 compact 后以 reviewer 视角自查一次。
- **低风险（小修改、纯文案、纯样式）**：执行者自检即可，但仍要走完工检查清单。

无论哪个层级，计划模板和完工清单都应保留 `review` 这一状态，让人类知道这里存在一个明确的审批点，而不是默认"执行完就算完成"。

### 6. 文档是跨会话的唯一记忆

Agent 没有长期记忆（Claude Code 的 memory 系统除外，但那更适合记用户偏好，不适合记项目状态）。上一次对话中 Agent 知道的所有事情，在下一次对话中全部丢失。唯一能跨会话传递信息的载体就是**仓库里的文件**。

代码改了但文档没跟上 → 下一次对话的 Agent 读到过时文档 → 基于错误信息做决策 → 产生连锁错误。

因此需要**完工检查清单**来机械化地保证文档同步。这不是建议，是硬约束——每次任务结束都必须走完清单，就像飞行员的起飞检查清单一样。

但完工检查清单解决的是"本次任务改了代码、是否同步了文档"——它防的是**即时遗忘**。另一种更隐蔽的腐化是**渐进漂移**：六个月后文档声称"使用 SQLite"，实际已被悄然迁移到 PostgreSQL，而中间没有任何一次任务显式触发过"改数据库"这一步。这种漂移无法靠完工清单发现，因为它不是某一次任务的遗漏，而是无数次微调的累积。

为此本 SKILL 内置了两层防线：**`scripts/audit.py`** 做机械检查（死链、STRUCTURE 索引完整性、依赖声明漂移、出生档案存在性、AGENTS.md 行数、同步一致性），**`docs/audit-checklist.md`** 做 Agent 手动裁决（设计决策仍成立？环境仍准确？未记录的变更？）。审计机制详见执行步骤第 9 步。

### 7. CHANGELOG 是高频写入的文件，必须脚本化操作

CHANGELOG 会随项目推进不断增长，可能达到几百甚至上千行。如果 Agent 每次写日志前都读取全文，会浪费大量上下文空间。更危险的是，Agent 可能在错误的位置插入条目，破坏倒序结构。

因此 CHANGELOG 有一套专门的脚本操作规则（详见 AGENTS.md 模板中的"CHANGELOG 规则"部分），核心是：**不读全文，通过 `scripts/changelog.py` 查看标题树、读取局部内容或追加条目。** 这把高频重复动作从上下文里挪到工具里，同时保留 Agent 对内容取舍的判断空间。当前任务状态不进入 CHANGELOG，由 `docs/CURRENT.md` 承担。

### 8. Occam 与 Bitter Lesson 是防止治理系统自增殖的护栏

初始化文档体系很容易走向"看起来更完整，实际上更重"：多加一个目录、多写一份规则、多列一个任务识别表，短期让 Agent 感觉更有把握，长期却会制造冷启动成本、一致性维护成本和规则漂移。

因此本 skill 将两条原则作为通用工程判断准则：

- **Occam's Razor**：如无必要，勿增实体。新增文件、脚本、字段、规则或流程前，必须能说清它解决的具体问题；如果只是让体系看起来完整，应拒绝。
- **Bitter Lesson**（源自 Rich Sutton，2019）：通用方法优于硬编码先验。长期来看，利用通用能力（模型理解、语义检索、结构化工具）比嵌入人类知识（关键词规则、任务模式枚举、提前分类）更有效。短期看，硬编码规则能让 Agent 快速上手；但长期看，它们会制造维护负担、抑制灵活性，最终成为演进障碍。优先设计能随计算/数据增长而自动扩展的元方法，而非预设具体场景的静态规则。

**两者的边界同样重要**：Occam 不反对必要复杂性，Bitter Lesson 也不反对结构性先验。同步脚本（agent_links.py）、CHANGELOG 脚本、计划文件这些结构之所以成立，是因为它们承载了可验证、重复发生、会消耗上下文的机械动作；相反，为每种未来任务预设规则表，就应先被这两条原则拦住。

具体的判别样例：

| 应保留的结构性先验 | 应避免的硬编码先验 |
|---|---|
| `agent_links.py` + copy 同步：承载"三文件同步"这个可验证、重复、会消耗上下文的动作 | 任务类型枚举表（"如果是 bug 修复就读 X，如果是新功能就读 Y"） |
| `changelog.py titles/show/add`：把"读全文"这个高频耗 token 动作下沉到工具 | CHANGELOG 条目的关键词分类规则（"必须以 fix:/feat: 开头并归到 X 类"） |
| 计划文件 + 状态机（queue/in_progress/review/completed）：承载跨上下文交接 | 给每种业务领域预先写好的"专属计划模板" |
| 完工检查清单：把易遗忘的硬约束机械化 | 用关键词匹配判断"任务是否需要复查" |

判别原则：先验如果能随项目演进自然扩展（脚本可加 flag、计划状态机可加新状态），且替代的是**确定会发生的、可机械化的**动作，就保留；先验如果是把"未来可能遇到的情况"提前枚举出来，就让它由 Agent 在具体上下文中判断，不要预编码。

### 9. 软约束靠文档，硬约束靠工具

AGENTS.md 里的规则本质上是"告诉 Agent 应该怎么做"，Agent 可能遗忘或违反。Pre-commit hook、lint、CI 是"强制 Agent 必须这样做"，Agent 绕不过去。

两者互补：文档说明意图和原因，工具保证执行。能用工具强制的规则，优先编码为工具而非文档。

**关键原则：对于必须要执行的操作，应通过机制强制执行，而不依赖 Agent 的判断力或记忆。**

| 约束类型 | 定义 | 例子 | 可靠性 |
|---|---|---|---|
| **硬约束** | 用脚本、hook、验证等机制强制执行 | Git pre-commit hook 检查 AGENTS.md 同步 | ✅ 可靠 |
| **软约束** | 依赖 Agent 记住并遵守的提醒 | 文件开头写提醒、完工检查清单 | ❌ 不可靠 |

**设计新规则时**：
- 优先考虑能否用代码强制（脚本、hook、自动化检查）
- 如果无法强制，在规则中明确声明为"必须"，并给出可验证的检查方法
- 避免"建议"、"提醒"等软约束措辞——这些在会话切换后会丢失

**AGENTS.md 同步的强制维护**：

AGENTS.md、CLAUDE.md、GEMINI.md 必须保持内容一致（因为不同 Agent 框架加载不同入口文件）。常见错误：

1. Agent 修改了 AGENTS.md，但忘记运行 `scripts/agent_links.py` 同步
2. Agent 直接修改了 CLAUDE.md 或 GEMINI.md（这是错误的）
3. 同步文件因编辑器原子写入行为而断开

**唯一正解：Git pre-commit hook 调用 `scripts/agent_links.py check`，断链/不一致时拒绝提交。** 具体落地见"执行步骤"第 6 步。脚本一处实现，hook 一行调用，不要在 hook 里再写一份独立的比对逻辑（避免双份维护成本和"工具缺失静默放行"的洞）。

---

## 目标文件结构

执行本 skill 后，**目标项目**应具备以下结构：

```
目标项目/
├── AGENTS.md              # 主文件（行为规则 + 导航）
├── CLAUDE.md              # → AGENTS.md 的同步副本
├── GEMINI.md              # → AGENTS.md 的同步副本
├── STRUCTURE.md           # 文档总索引（一张导航表）
├── CHANGELOG.md           # 变更记录（倒序，最新在前）
├── scripts/
│   ├── changelog.py       # CHANGELOG 的 token-light 操作入口
│   ├── agent_links.py     # AGENTS/CLAUDE/GEMINI 同步检查与修复
│   └── audit.py            # 文档一致性机械检查（死链/漂移/结构）
├── .githooks/             # （可选）质量门控
│   └── pre-commit
├── docs/
│   ├── CURRENT.md         # 当前任务状态（单 owner handoff / 全局入口）
│   ├── overview.md        # 系统主线与设计决策
│   ├── api.md             # API 约定（如有 API 的项目）
│   ├── deployment.md      # 部署与环境配置
│   ├── pitfalls.md        # 已知环境陷阱
│   ├── audit-checklist.md # 文档一致性审计清单（Agent 手动裁决用）
│   └── plans/
        ├── active/        # 进行中的执行计划
        │   └── .gitkeep
        └── completed/     # 已完成的执行计划
            ├── .gitkeep
            └── initialization.md   # 初始化本身作为第一份已完成计划（见第 0 步）
```

**注意**：根据项目实际情况可增减 `docs/` 下的文件，但上述是推荐的最小集。没有 API 的项目可以不建 api.md；纯后端项目可能不需要 pitfalls.md（前端环境陷阱通常更多）。但 overview.md 和 deployment.md 几乎任何项目都需要。

## 本 skill 的 assets 目录

```
init-agent-docs/
└── assets/
    ├── templates/
    │   └── zh/                       # 中文模板集
    │       （AGENTS, STRUCTURE, CURRENT, overview, api, deployment,
    │        pitfalls, plan, CHANGELOG, audit-checklist — 共 10 个 .tpl 文件）
    ├── scripts/
    │   ├── changelog.py              # CHANGELOG 标题树 / 局部读取 / 追加
    │   ├── agent_links.py            # AGENTS/CLAUDE/GEMINI 同步检查与修复
    │   └── audit.py                  # 文档一致性机械检查（死链/漂移/结构完整性）
    ├── references/
    │   ├── workflow-patterns.md      # 执行计划工作流与跨上下文协作详细说明
    │   └── eval-baseline.md          # Skill 质量评估框架与测试用例
    ├── hooks/
    │   ├── pre-commit-python.sh
    │   ├── pre-commit-node.sh
    │   ├── pre-commit-go.sh
    │   ├── pre-commit-generic.sh
    │   └── pre-commit-config.yaml    # pre-commit 框架样例
    └── pitch/
        └── presentation.html         # 对外宣讲 deck（非运行时产物，可忽略）
```

---

## 执行步骤

### 第 0 步：先澄清意图，再选择工作模式

不要把这一阶段当成"机械回答 7 个问题"。更好的做法是采用 **intent-first / deep-interview** 思路：先读仓库里最高价值的事实源，必要时再向用户追问，逐步澄清项目画像；**当你已经掌握足够信息，能够可靠地填写模板时，才进入第 1 步**。

**先调查高价值来源（按优先级）**：

1. `README*`、根目录 manifest、workspace 配置、lockfile（如 `package.json` / `pnpm-workspace.yaml` / `pyproject.toml` / `go.mod` / `Cargo.toml` / `requirements*.txt`）
2. 构建、测试、lint、format、typecheck、codegen 配置，以及 task runner / pre-commit 配置
3. CI 工作流（如 `.github/workflows/*`），因为它通常暴露真实验证命令和命令顺序
4. 现有 instruction 文件：`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`.cursor/rules/**`、`.cursorrules`、`.github/copilot-instructions.md`
5. repo-local OpenCode 配置：`opencode.json` / `opencode.jsonc` / `.opencode/opencode.json`
6. 如果架构仍不清楚，再读少量能说明系统如何串起来的入口文件、路由文件、workspace package 边界文件；不要随机读叶子文件

**裁决规则**：可执行事实源优先于 prose 文档。命令、工具链、测试入口、lint/format/typecheck/codegen 顺序，以 CI / hook / task runner / manifest scripts / lockfile / config 为准；README、旧文档和模板默认文案只能作为线索。仓库已经能回答的问题不要问用户；只在仓库无法回答关键决策时提问，但初始化规模、是否启用 hook、是否覆盖旧 agent 指令文件仍必须由用户确认。

在上述调查基础上，至少澄清以下维度：

1. **项目做什么？**（一句话概括，这决定了 overview.md 的开头）
2. **技术栈是什么？**（语言、框架、前后端分离？这影响代码风格约定和 pre-commit 片段选择）
3. **有哪些硬约束？**（密钥管理、构建产物路径、特殊部署方式、合规要求）
4. **当前有没有已存在的文档？** 需要迁移还是从零开始？如果已有文档，哪些内容值得保留？（决定是否要走第 3 步的迁移流程）
5. **项目使用哪些 AI Agent？**（Claude Code、Codex、Gemini CLI、Cursor 等——这决定需要哪些同步文件名）
6. **项目的构建产物在哪里？**（dist/、build/、data/、node_modules/ 等——这些路径需要写入硬约束）
7. **项目有没有自动化测试？** 测试命令是什么？这决定了测试要求部分怎么写。
8. **这个项目的默认协作倾向是什么？**（通常是单 Agent 顺序推进，还是经常多 Agent / 多窗口并行？这是默认倾向，不是对每个任务的一刀切规定）
9. **这个项目更常见的是哪类任务？**（小修改、分阶段任务，还是需要 reviewer / verifier 的高风险改动？）
10. **文档语言？** 当前模板仅提供中文（`assets/templates/zh/`）。如目标项目以英文为主，需要先把 zh 模板翻译成英文再使用，或在初始化后人工改写——本 skill 不再附带英文模板。

在落文档前，先根据项目的默认倾向写出协作偏好；**具体到每个任务开始前，再显式选择一种工作模式**：

- **直接执行模式**：小任务、低风险修改，不建详细计划；`docs/CURRENT.md` 写 1-3 行即可。
- **分阶段模式**：中等复杂度任务，需要计划文件，但通常仍是单 owner 顺序推进。
- **协作模式**：高复杂度或高风险任务，存在多 Agent / 多窗口并行，计划文件中必须包含任务分配、领取状态和复查节点。

如果用户没有明确说明，默认从轻量模式开始；一旦任务跨模块、跨会话或需要并行，就升级到更重的模式。**不要在初始化阶段把某个模式永久写死给整个项目**。

---

**规模与模式决策（必须得到用户确认）**

根据以上 10 个维度的信息，向用户展示以下选项的差异，由用户拍板选择初始化规模：

| 选项 | 规模定义 | 创建哪些文件 | plans/ 目录 | 典型场景 |
|------|---------|------------|------------|---------|
| **小型** | 脚本/工具，核心文件 < 5 个 | AGENTS.md + CHANGELOG.md + docs/CURRENT.md | **不建** | 单次会话能完成的工具脚本 |
| **中型** | 单体应用，5–30 个文件 | 全套：STRUCTURE.md + docs/*（overview/deployment/pitfalls） | active + completed | 需要长期维护的独立应用 |
| **大型** | 多模块/微服务，> 30 个文件 | 中型全套 + 模块级拆分提示 | active + completed + 模块子计划 | 多团队协作的复杂系统 |

**执行原则：**
- 默认从轻量开始，但**必须向用户说明推荐理由并征得同意**，例如："根据项目规模和任务类型，建议选择中型初始化，创建全套 docs/ 和 plans/ 目录。是否确认？"
- **不要在未得到用户同意前擅自决定**。如果用户说"先简单来"，就按小型执行；如果用户说"全套"，就按中型或大型执行。
- 用户的拍板结果必须记录下来，作为后续步骤的输入依据。

**把 intent 结果落盘。** 第 0 步收集的信息（包括用户确认的规模选择）不要只留在对话里——初始化完成后，它就是这份文档体系的"出生档案"。建议第 5 步结束时把 10 个维度的答案 + 用户确认的规模写入：

- 中型 / 大型项目：`docs/plans/completed/initialization.md`（用 `plan.md.tpl` 作骨架）
- 小型项目：`docs/initialization.md`（小型项目不建 plans 目录，直接放在 docs/ 下，用一份精简骨架即可——目标 / 规模 / 10 个维度的答案 / 完成时间）

将来审计或重构文档体系时就有据可查。

---

### 第 1 步：创建 AGENTS.md 及同步副本

1. 读 `assets/templates/zh/AGENTS.md.tpl`（当前 skill 仅附带中文模板）。
2. 基于模板生成目标项目的 `AGENTS.md`。模板里：
   - `[方括号]` 是"替换为具体值"的占位
   - `<!-- HTML 注释 -->` 是给你的填写指导，生成最终文件时应替换为实际内容或整段删除
3. 使用第 0 步收集的信息裁剪和填充：
   - "信息导航"一节：没 API 删 api.md 行，没部署删 deployment.md 行
   - "硬约束"一节：填入项目的构建产物路径、特殊约束
   - "测试要求"一节：按有无测试套件填
   - 添加代码风格约定（语言 / 缩进 / 命名）
4. 先把脚本资产复制到目标项目：

   ```bash
   mkdir -p scripts
   cp assets/scripts/changelog.py scripts/
   cp assets/scripts/agent_links.py scripts/
   ```

   Windows / PowerShell 等价操作：

   ```powershell
   New-Item -ItemType Directory -Force scripts
   Copy-Item assets\scripts\changelog.py scripts\
   Copy-Item assets\scripts\agent_links.py scripts\
   ```

5. **如目标项目已有任一 instruction 文件**（`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`.cursor/rules/**`、`.cursorrules`、`.github/copilot-instructions.md`、repo-local `opencode.json` / `opencode.jsonc` / `.opencode/opencode.json` 等），**先读取它们的内容**，提取新 AGENTS.md 尚未覆盖的硬约束、精确命令、工具链顺序、测试/单包验证方式、monorepo 边界、Agent 行为限制和禁止事项，整合到新生成的 AGENTS.md 中，然后再执行 repair。不要未经阅读就直接覆盖——旧文件中往往包含用户已经验证过的项目画像和运行方式。若存在冲突，按第 0 步的"可执行事实源优先"规则裁决，并把重要取舍记录到出生档案。

6. 写入目标项目的 `AGENTS.md` 后，运行同步脚本，将 `AGENTS.md` 的内容复制到 `CLAUDE.md` 和 `GEMINI.md`，并验证三文件一致：

   ```bash
   python scripts/agent_links.py repair
   python scripts/agent_links.py check
   ```

7. 如果检查失败，先确认 `CLAUDE.md` / `GEMINI.md` 是否含有不同内容；确认可以用 `AGENTS.md` 覆盖后再修复：

   ```bash
   python scripts/agent_links.py repair
   # 内容不同且已人工确认时才使用：
   python scripts/agent_links.py repair --force
   ```

**默认使用 copy 模式**：`repair` 默认以 copy 模式工作（`--mode=copy`），将 `AGENTS.md` 的内容复制到 `CLAUDE.md` 和 `GEMINI.md`，并用 MD5 校验一致性。copy 模式的优势是**不受编辑器原子写入影响**——部分编辑器保存时用"写临时文件 → 删原文件 → 重命名"，会创建新 inode 从而断开硬链接；copy 模式不存在这个问题。

```bash
python scripts/agent_links.py repair          # 默认 copy 模式
python scripts/agent_links.py check           # 默认接受 copy 或 hardlink 任一状态
```

**如文件系统支持且你明确需要 hardlink**：显式传 `--mode=hardlink` 锁定模式。但请注意，hardlink 在以下场景会断裂：编辑器原子写入、WSL 跨盘、ReFS/exFAT、部分 CI 容器。断裂后需要重新运行 `repair` 恢复。在 AGENTS.md 顶部写清当前项目用哪种模式，避免歧义。

```bash
python scripts/agent_links.py repair --mode=hardlink
python scripts/agent_links.py check  --mode=hardlink
```

### 第 2 步：创建 STRUCTURE.md 和 docs/ 目录

**根据第 0 步用户确认的规模，按以下分支执行：**

#### 小型项目
只生成以下文件：
- `CHANGELOG.md`（从 `CHANGELOG.md.tpl`）
- `docs/CURRENT.md`（从 `CURRENT.md.tpl`）

**不生成** `STRUCTURE.md`、`docs/overview.md`、`docs/deployment.md`、`docs/pitfalls.md`。
**不建** `docs/plans/` 目录。

**对应裁剪 AGENTS.md（必做）**：第 1 步生成的 AGENTS.md 默认信息导航包含全套指针。小型项目要回到 AGENTS.md 删除以下行，避免死链：

- `文档总索引：[STRUCTURE.md]...`
- `系统主线与设计决策：[docs/overview.md]...`
- `API 约定：[docs/api.md]...`
- `部署与同步：[docs/deployment.md]...`
- `环境陷阱：[docs/pitfalls.md]...`
- `复杂任务计划：[docs/plans/]...`

只保留 `当前任务状态：docs/CURRENT.md` 和 `变更记录：CHANGELOG.md` 两条。同时删除 AGENTS.md 中"文档维护原则"里关于 `docs/overview.md` / `docs/api.md` / `docs/deployment.md` / `docs/pitfalls.md` / `docs/plans/active/` 的所有指针段（小型项目不存在这些文件）。

裁剪后运行 `python scripts/agent_links.py repair` 把改动同步到 CLAUDE.md / GEMINI.md。

#### 中型项目
按模板生成以下全套文件：

| 目标路径 | 模板 |
|---------|------|
| `STRUCTURE.md` | `STRUCTURE.md.tpl` |
| `docs/CURRENT.md` | `CURRENT.md.tpl` |
| `docs/overview.md` | `overview.md.tpl` |
| `docs/api.md`（可选） | `api.md.tpl` |
| `docs/deployment.md` | `deployment.md.tpl` |
| `docs/pitfalls.md`（可选） | `pitfalls.md.tpl` |
| `docs/audit-checklist.md` | `audit-checklist.md.tpl` |
| `CHANGELOG.md` | `CHANGELOG.md.tpl` |

然后建立计划目录：

```bash
mkdir -p docs/plans/active docs/plans/completed
touch docs/plans/active/.gitkeep docs/plans/completed/.gitkeep
```

#### 大型项目
生成中型项目的全套文件，并额外在 AGENTS.md 或 `docs/overview.md` 中加入提示：
> 后续按模块拆分时，每个模块可建独立的 `docs/<module>/` 子目录和独立的 `docs/plans/active/<module>-*.md` 计划文件。

然后同样建立 `docs/plans/active` 和 `docs/plans/completed`。

---

**不要留空文件**——至少写一个标题 + 一句话说明文件的定位，否则 Agent 不知道该往里写什么。模板指导注释只供生成前理解，不是最终内容；最终目标项目文件不得残留 HTML 指导注释或 `[方括号]` 占位符。

### 第 3 步（条件性）：迁移已有文档

**仅当目标项目已有 README / ARCHITECTURE / ONBOARDING / docs/ 等文档时执行。** 从零开始的项目跳过这一步。

迁移的目标不是"删掉旧的一切"，而是**把有价值的信息归口到新结构里**，同时避免信息在两处并存腐烂。

1. **盘点**：`find . -maxdepth 3 \( -iname 'README*' -o -iname 'ARCHITECTURE*' -o -iname 'CONTRIBUTING*' -o -iname 'ONBOARDING*' -o -iname 'DESIGN*' -o -iname 'DEPLOY*' \)` 列出所有候选。用 Glob 也可以。
2. **分类**：对每份旧文档的每一节，按以下规则决定去向：

   | 旧文档的内容 | 新位置 |
   |------------|--------|
   | 系统设计决策、架构图、选型理由 | `docs/overview.md` |
   | API 端点约定、错误格式 | `docs/api.md` |
   | 环境变量、部署步骤、启动方式 | `docs/deployment.md` |
   | 已知坑、环境问题、兼容性陷阱 | `docs/pitfalls.md` |
   | 目录结构、文件职责列表、函数签名 | **丢弃**（违反"只记代码读不出来的东西"） |
   | 项目简介、面向谁、谁维护 | 留在 `README.md`（面向人类读者） |
   | 行为规则、协作约定 | `AGENTS.md` 的硬约束 / 默认偏好 |

3. **去重与裁决**：如果一条信息在多份旧文档里都出现，只保留一份。区分两类冲突：
   - **信息归口冲突**：同一类信息应该放在哪里，以新文档结构为准（例如设计决策归 `docs/overview.md`，CHANGELOG 只记摘要）。
   - **事实内容冲突**：命令、入口、工具链顺序、测试方式、生成物路径等，以可执行来源为准，优先级为 CI / hook / task runner / manifest scripts / lockfile / config > README / prose docs > 模板默认文案。
4. **标注废弃**：旧文档如果整体被拆分迁移，在顶部加一条"**⚠️ 本文件的内容已迁移至 docs/ 及 AGENTS.md。保留此文件仅供历史追溯，后续更新请前往对应新位置。**"——不要立刻删除，让 git blame / PR 评论等历史引用还能找到。
5. **记录到 CHANGELOG**：用 `python scripts/changelog.py add ...` 把本次迁移作为一次独立变更记录。

### 第 4 步：初始化首个计划文件（可选）

如果用户的下一个任务已经明确、且是分阶段或协作模式，就基于 `assets/templates/zh/plan.md.tpl` 在 `docs/plans/active/` 下创建第一份计划，顺便校验这个模板在具体任务上好不好用。

如果当前没有待启动的任务，跳过本步骤——计划应该按需创建，而不是放空壳进去。

### 第 5 步：记录初始化本身

把第 0 步收集到的 intent 答案写入"出生档案"文件：

- 中型 / 大型项目：`docs/plans/completed/initialization.md`，用 `plan.md.tpl` 作骨架，状态直接标 `✅ completed`
- 小型项目：`docs/initialization.md`，精简骨架即可（目标 / 规模 / 10 个维度的答案 / 完成时间），不必复用 plan 模板

这一步有两个作用：
- 将来重新审视文档体系时，可以对照出生档案看哪些假设已变
- 中型 / 大型项目顺便给未来的 Agent 一个具体范例：计划文件长什么样、怎么填

同时用脚本写入 CHANGELOG，不要手工打开全文：

```bash
python scripts/changelog.py add \
  --title "初始化文档体系" \
  --body "建立 agent-first 文档结构：AGENTS.md（含同步副本 CLAUDE.md / GEMINI.md）+ STRUCTURE.md + docs/ 层级；配置 scripts/changelog.py 与 scripts/agent_links.py，脚本化维护日志和同步副本；迁移/整合旧文档（如适用）：见 docs/plans/completed/initialization.md"
```

### 第 6 步：初始化质量门控

**强烈推荐执行，不要因为"只是文档"就跳过**——能用工具强制的规则就不要只靠文档（设计哲学第 9 条）。

1. 确认脚本已经复制到项目：

   ```bash
   python scripts/changelog.py titles --limit 3
   python scripts/agent_links.py check
   ```

2. **确认 git 仓库已初始化**。如果项目根目录没有 `.git/`，pre-commit hook 无法生效。此时先执行：

   ```bash
   git init
   ```

3. **配置 pre-commit hook（必须）**——核心目的是在每次提交前检查 `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 三文件内容是否一致，防止 Agent 修改 AGENTS.md 后忘记同步。assets 下的 hook 已内建 fallback：优先调用 `agent_links.py`，不可用时用内联 MD5 检查（兼容 md5sum / md5），工具缺失时警告但不阻塞。

   **二选一，不要叠加**——assets 下的技术栈 hook 内部已经包含 agent_links 一致性检查，再叠加 inline 的最小 hook 会让检查跑两次、输出混乱。

   **路径 A：项目没有特殊 lint 需求 → 直接用 inline 最小 hook**

   ```bash
   mkdir -p .githooks
   cat > .githooks/pre-commit << 'EOF'
   #!/usr/bin/env bash
   set -e
   python scripts/agent_links.py check || {
       echo ""
       echo "AGENTS.md / CLAUDE.md / GEMINI.md 内容不一致。"
       echo "正确流程：仅编辑 AGENTS.md，然后运行 python scripts/agent_links.py repair。"
       exit 1
   }
   EOF
   chmod +x .githooks/pre-commit
   git config core.hooksPath .githooks
   ```

   **路径 B：项目需要 lint / format 检查 → 直接复制对应技术栈 hook**

   `assets/hooks/pre-commit-*.sh` 已经在内部调用了 `scripts/agent_links.py check`，所以不要再叠加路径 A 的 inline 版本。

   - Python 项目 → `assets/hooks/pre-commit-python.sh`
   - Node/TS 项目 → `assets/hooks/pre-commit-node.sh`
   - Go 项目 → `assets/hooks/pre-commit-go.sh`
   - 混合 / 特殊栈 → `assets/hooks/pre-commit-generic.sh`（自行补 lint 命令）
   - 已在用 pre-commit 框架 → `assets/hooks/pre-commit-config.yaml` 贴到项目根的 `.pre-commit-config.yaml`

   ```bash
   mkdir -p .githooks
   cp assets/hooks/pre-commit-python.sh .githooks/pre-commit   # 按栈替换文件名
   chmod +x .githooks/pre-commit
   git config core.hooksPath .githooks
   ```

   PowerShell 等价：

   ```powershell
   New-Item -ItemType Directory -Force .githooks
   Copy-Item assets\hooks\pre-commit-python.sh .githooks\pre-commit
   git config core.hooksPath .githooks
   ```

   `agent_links.py check` 在以下情况返回非 0：三文件之一缺失、不属于同一个 inode、或内容已分叉。Python 解释器缺失时也会自然失败——比 bash 内联用 `md5sum` 然后在工具缺失时 `exit 0` 安全。

   **Windows 注意**：hook 是 bash 脚本，需要 git bash 解释（绝大多数 Windows 安装 Git for Windows 时已自带）。如果项目要求纯 PowerShell 路径，改用下面的 `pre-commit` 框架方案（跨平台）。

   **路径 C：使用 `pre-commit` 框架（推荐给跨平台 / 多语言混合项目）**

   `pre-commit` 是一个跨平台的 hook 管理工具，能在 Windows / Linux / macOS 上一致地执行 Python 写的 hook，且自动处理 git hook 安装、版本固定、虚拟环境隔离。安装即用：

   ```bash
   pip install pre-commit
   cp assets/hooks/pre-commit-config.yaml .pre-commit-config.yaml
   pre-commit install
   ```

   PowerShell 等价：

   ```powershell
   pip install pre-commit
   Copy-Item assets\hooks\pre-commit-config.yaml .pre-commit-config.yaml
   pre-commit install
   ```

   `assets/hooks/pre-commit-config.yaml` 已经包含 `agent_links.py check` 这一条 local hook（始终启用），其他语言 lint 段落以注释形式给出，按项目实际栈解开注释即可。这条路径与路径 A / B 互斥——选了它就不要再用 `git config core.hooksPath .githooks`，`pre-commit install` 会接管 `.git/hooks/pre-commit`。

4. 本地触发一次确认能通过（可选——CI 矩阵已覆盖这些用例，跳过也行）：

   ```bash
   # 期望：直接提交一次空改动应通过
   git commit --allow-empty -m "test: hook pass" && git reset --soft HEAD~1

   # 期望：人为破坏 CLAUDE.md 后提交应被拒绝
   echo "diverged" >> CLAUDE.md && git add CLAUDE.md
   git commit -m "test: hook reject" && echo "BUG: hook should have rejected" || echo "ok: hook rejected as expected"
   git restore --staged CLAUDE.md && git checkout -- CLAUDE.md
   python scripts/agent_links.py repair
   ```

   `git reset --soft HEAD~1` 仅撤回 commit 不动工作区；如果该 commit 是仓库的第一次 commit，跳过这条命令（无 HEAD~1 可回退）。

### 第 7 步：静态自检

**通用项（所有规模都要过）：**

1. 所有应创建的文件已创建且路径正确（按第 0 步用户确认的规模判断"应创建"的范围，不要按全套查）
2. `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 同步一致：`python scripts/agent_links.py check` 返回 0
3. `AGENTS.md` 中的所有链接指向真实存在的文件——**这一条对小型项目最关键**：默认模板的信息导航包含 STRUCTURE.md / overview.md / api.md / deployment.md / pitfalls.md / docs/plans/ 全部指针，小型项目必须按第 2 步要求裁剪掉
4. `docs/CURRENT.md` 已创建，并在 `AGENTS.md` 的信息导航中可访问
5. `CHANGELOG.md` 可由 `python scripts/changelog.py titles --limit 5` 输出至少一条标题（说明第 5 步的 `add` 成功写入了初始化条目）
6. `python scripts/audit.py check` 退出码为 0（或仅有预期的 `[MISS]` 出生档案项——如果出生档案还未写入的话）
7. 最终目标项目文件不得残留 HTML 指导注释或 `[方括号]` 占位符；这些只属于模板，不属于交付物
8. `AGENTS.md` 行数不超过约 200 行（超出说明有内容该下沉到 docs/，或小型项目漏裁剪）

**中型 / 大型项目额外项：**

8. `STRUCTURE.md` 中的索引表与 `docs/` 下的文件一一对应（多了或少了都修）
9. `docs/audit-checklist.md` 已创建，且 `STRUCTURE.md` 索引表中包含其链接
10. `docs/plans/active/` 和 `docs/plans/completed/` 目录存在
11. 出生档案 `docs/plans/completed/initialization.md` 已写入

**小型项目额外项：**

8. 出生档案 `docs/initialization.md` 已写入（不是 `docs/plans/completed/initialization.md`）
9. `docs/audit-checklist.md` 已创建，且 AGENTS.md 信息导航中包含其链接
10. 没有创建 `docs/plans/`、`STRUCTURE.md`、`docs/overview.md` 等文件——如果创建了说明规模分支判断错

### 第 8 步：reviewer-perspective 自检（必做）

这一步是对设计哲学第 5 条的兑现——**不要让"执行者自检"冒充"已验证"。**

**为什么把它定为必做级（而不是按哲学第 5 条的"中等风险 → 建议级"）**：单次任务的 reviewer 可以"看情况"，因为它的影响半径是这一次任务；但 AGENTS.md 是后面几十次对话的入口文档，一旦规则模糊或导航指针断链，**所有后续会话都会带着病上路**——影响半径远超一次中等风险改动。所以这里把分级提升到"必做"，等同于哲学第 5 条里"高风险 / 跨模块改动"的处理。

做法：

1. **新开一个 Agent 窗口或启动 subagent**：
   - 新窗口：打开新的 Claude Code 窗口或新会话
   - Subagent：使用 Agent 工具启动子 agent（如 code-reviewer）
2. 让它**只读 AGENTS.md**，不看其他文件，然后回答：
   - 这个项目做什么？
   - 我不能改哪些文件？
   - 任务完成时我需要做什么？
   - 如果接到一个复杂任务，我应该先去哪里？
3. 如果回答含糊或错误，说明 AGENTS.md 没写清楚——回去改，直到新上下文能通过这个测试为止

这个测试的成本很低（十几分钟），但收益极高：它验证的恰恰是 AGENTS.md 作为"入口地图"最核心的功能。**未通过本步前不要向用户报告"初始化已完成"。**

初始化完成后，把第 0 步回答 + 自检结果追加到出生档案的"完成记录"里：中型 / 大型项目写入 `docs/plans/completed/initialization.md`，小型项目写入 `docs/initialization.md`。

---

### 第 9 步：初始化审计能力

这一步补上设计哲学第 6 条揭示的"渐进漂移"防线。审计分两层：`scripts/audit.py` 做机械检查，`docs/audit-checklist.md` 做 Agent 手动裁决。

1. 复制审计脚本到目标项目：

   ```bash
   cp assets/scripts/audit.py scripts/
   ```

   PowerShell 等价：

   ```powershell
   Copy-Item assets\scripts\audit.py scripts\
   ```

2. 基于模板创建审计清单——**所有规模都要创建**：

   - 读 `assets/templates/zh/audit-checklist.md.tpl`
   - 写入 `docs/audit-checklist.md`
   - 模板已可直接使用，无需裁剪

3. **更新 STRUCTURE.md 索引表**：在表格中新增一行：

   ```markdown
   | 文档一致性审计 | [docs/audit-checklist.md](docs/audit-checklist.md) |
   ```

4. **更新 AGENTS.md 信息导航**：在 `docs/` 指针段末尾追加：

   ```markdown
   - 文档一致性审计：[docs/audit-checklist.md](docs/audit-checklist.md)
   ```

5. 本地试跑确认脚本能执行：

   ```bash
   python scripts/audit.py check
   ```

   初始化完成时通常是干净的（无死链、无漂移、行数正常），脚本应退出 0。如果有 `[MISS]` 出生档案项——那是正常的，出生档案要到第 5 步才写入；但其他项不应该出现。

   **小型项目注意**：因为不建 `STRUCTURE.md`，`audit.py structure` 会输出 0 条结果（相当于跳过），不会报错。不需要为小型项目裁剪 `audit.py` 本身。

---

## 执行计划与跨上下文工作流

复杂任务需要跨上下文窗口交接。计划文件是不同 Agent / 会话之间的唯一记忆载体，其详细设计 rationale 见设计哲学第 4 条。

执行计划的具体工作模式（单 Agent 顺序推进 vs 多 Agent 并行协作）、git worktree 用法、阶段粒度控制、协调人职责，以及计划文件的生命周期管理，详见 `assets/references/workflow-patterns.md`。

计划模板在 `assets/templates/zh/plan.md.tpl`。关键字段包括任务分配表、阶段划分、决策记录、风险与遗留。

## 模式选择与裁剪指南

### 按工作模式选择

| 模式 | 适用场景 | 最低要求 |
|------|---------|---------|
| 直接执行模式 | 小修改、低风险、一次会话内能完成 | AGENTS.md + `docs/CURRENT.md` 一行摘要 |
| 分阶段模式 | 中等复杂度、可能跨会话 | AGENTS.md + `docs/CURRENT.md` + `docs/plans/active/*.md` |
| 协作模式 | 多 Agent / 多窗口并行，高风险改动，需要 reviewer | 分阶段模式全部内容 + 任务分配表 + claim/review 状态流转 |

### 按项目规模裁剪

| 项目规模 | 建议保留 | 可省略 |
|---------|---------|--------|
| 小型脚本/工具 | AGENTS.md + CHANGELOG.md + docs/CURRENT.md | docs/ 专题文档、STRUCTURE.md |
| 中型单体应用 | 全部 | 根据需要省略 api.md 或 pitfalls.md |
| 大型多模块项目 | 全部 + 按模块拆分 docs/ | 无 |

对于小型项目，可以把 overview.md 的内容直接放在 AGENTS.md 的信息导航区域下方（只要 AGENTS.md 不超过 200 行）。但一旦项目开始增长，就应该及时拆分。

---

## 反模式（避免）

1. **巨型 AGENTS.md**：把所有规则、架构、API 文档塞进一个文件。Agent 上下文是稀缺资源，挤占了代码和任务的空间，反而降低 Agent 效果。解法：AGENTS.md 只放指针，内容下沉到 docs/。

2. **重复代码能看到的东西**：文档写目录结构、函数签名、参数默认值。这些信息会随代码变化，文档无法自动同步，必然腐烂。解法：只写"为什么"，不写"是什么"。

3. **没有完工检查**：代码改了文档没跟上，下次对话 Agent 基于过时信息决策，产生连锁错误。解法：完工检查清单作为硬约束写入 AGENTS.md。

4. **计划只在对话里**：复杂任务在对话中讨论了计划，但没有落文件。上下文压缩或新会话后，计划丢失，Agent 从零开始。解法：计划必须落到 `docs/plans/active/`。

5. **计划不分阶段或阶段太大**：一个阶段涉及 30 个文件的修改，一个上下文窗口做不完，中途 compact 后 Agent 不知道做到哪了。解法：按上面的粒度指南拆分阶段，每阶段完成后更新计划文件。

6. **并行协作还在写单例 CURRENT.md**：多个 owner 同时推进，却只有一个全局"当前状态"文件，结果谁覆盖谁。解法：并行时把任务分配和状态流转放进计划文件，CURRENT.md 只保留入口或协调摘要。

7. **把执行完成当成验证完成**：同一个上下文里写完代码就直接勾选"已完成"，没有 `review` 节点。解法：给计划和清单加入待验证状态，重要任务用新上下文或 reviewer 视角复查。

8. **文档只增不删**：过时文档比没有文档更危险——Agent 会信以为真。解法：定期审视文档，删除或更新过时内容。

9. **信息散落多处**：同一个事实在三个文件里各写一遍，改了一处忘了其他。解法："不重复"原则，同一信息只在最合适的位置出现一次。

10. **每次写日志都读全文**：CHANGELOG 可能很长，读全文浪费上下文且容易在错误位置插入。解法：用 `scripts/changelog.py titles/show/add` 做标题树查看、局部读取和追加，不读全文。

11. **CURRENT.md 与 plans 空转**：为所有项目无脑创建全套 docs/ 层级和 plans 目录，结果 CURRENT.md 永远写着"无"，plans/active/ 只有一个 .gitkeep。Agent 从不读取和更新，文档体系沦为摆设。解法：初始化时按项目规模裁剪——小型项目只保留 AGENTS.md + CHANGELOG.md + CURRENT.md；在 AGENTS.md 中写明"任务启动先读 CURRENT.md"和"什么情况下才建计划"的触发条件。

12. **全靠软约束**：所有规则都写在 AGENTS.md 里，没有机械化验证。Agent 在长上下文中容易遗忘或违反。解法：能用 hook/lint/CI 强制的规则，编码为工具（典型例子是 AGENTS.md 同步——见哲学第 9 条与第 6 步）。

13. **关键原则只存在于对话中**：某次对话中确认了"硬约束优先"，但没有写入 AGENTS.md。新对话开始时 Agent 完全不知道这个原则的存在。解法：重要原则必须写入文档（AGENTS.md 的准则段），这样每次新对话都会自动加载。

14. **初始化完就不自检**：AGENTS.md 写完自己读一遍觉得没问题就结束。但执行者在同一上下文里天然有确认偏误。解法：第 8 步的 reviewer-perspective 自检——如果能启动 subagent，就启动一个 subagent 让它只读 AGENTS.md 审计初始化情况；如果不能，至少让一个新上下文只看 AGENTS.md 回答几个关键问题。

15. **为了完整感复制治理形式**：看到多层规则、完整组织隐喻或复杂流程，就照搬到新仓库。解法：只保留能解决真实问题的原则和结构；具体形式必须由目标项目的实际约束长出来。

16. **迁移时直接删旧文档**：历史引用瞬间失效。解法：第 3 步先标"已迁移"，保留一段时间再彻底删除。
