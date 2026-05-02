---
name: init-agent-docs
description: Initialize an agent-first documentation system for a project. Use when setting up a new repository's doc structure for AI agent collaboration, or when migrating an existing project to agent-friendly documentation. This skill creates the scaffolding files (AGENTS.md, architecture index, docs/ hierarchy, changelog, plans directory) and populates them with starter content tailored to the target project.
---

# Init Agent Docs

为项目创建面向 AI Agent 的文档体系。核心理念来自 OpenAI Codex 团队的工程实践：**仓库即知识系统的唯一事实源，Agent 看不到的等于不存在。**

本 skill 仅用于初始化，不会驻留在 Agent 上下文中，因此不必节省篇幅。下面会详细解释每个设计决策的"为什么"，确保执行本 skill 的 Agent 充分理解意图，而不是机械地复制模板。

**本 skill 的模板和脚本存放在 [assets/](assets/) 下**；执行步骤里会告诉你什么时候 `Read` 哪个文件、`Write` 到目标项目的哪个路径。维护说明见 [README.md](README.md)。

---

## 设计哲学

### 1. AGENTS.md 是目录，不是百科全书

> "Give Agents a map, not a 1,000-page instruction manual."

AGENTS.md（及其硬链接 CLAUDE.md、GEMINI.md）是 Agent 上下文中**始终驻留**的文件。这意味着它的每一行都在消耗 Agent 的注意力预算。一个 500 行的 AGENTS.md 会挤占任务描述、代码和文档的空间，导致 Agent "什么都看到了但什么都没注意"。

**AGENTS.md 的职责边界：**

| 应该放的 | 不应该放的 |
|---------|----------|
| 硬约束（不可违反的规则） | 模块职责、函数签名 |
| 默认偏好（可偏离的约定） | 目录结构描述 |
| 信息导航（指向 docs/ 的指针） | API 端点列表 |
| 完工检查清单 | 部署步骤详情 |
| 文档维护规则 | 设计决策的详细论述 |

**为什么用硬链接？** 不同 Agent 框架加载不同文件名：Claude Code 加载 CLAUDE.md，Codex 加载 AGENTS.md，Gemini CLI 加载 GEMINI.md。硬链接让三个文件始终是同一个文件的不同入口，编辑任何一个都会同步到其他两个，避免内容漂移。

**建议控制在 100 行以内。** 如果超过了，说明有些内容应该下沉到 docs/ 中，AGENTS.md 只留指针。

### 2. 渐进式披露（Progressive Disclosure）

Agent 从一个小而稳定的入口出发，按需深入查阅。这和给新员工入职一样——先给地图，再让他自己去探索，而不是第一天就塞一本 500 页的手册。

信息分层结构：

```
AGENTS.md          → 行为规则 + 导航指针（始终在上下文，~100 行）
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

详见下方"执行计划模板与跨上下文工作流"部分。

### 5. 验证应被视为独立视角，而不只是执行者自检

同一个 Agent 在同一个上下文窗口里做完实现，再立刻说"我已经验证过了"，天然带有确认偏误。它刚写完代码，最容易忽略自己埋下的问题。

因此文档体系里应显式给"验证"留位置。最理想的情况是：
- 执行者负责实现和自检
- 另一个新上下文 Agent，或至少 compact 后的 reviewer 视角，负责复查和验收

你不一定每次都真的起两个进程，但计划模板和完工清单应当预留 `待验证` / `待复查` 这类状态，让人类知道这里存在一个明确的审批点，而不是默认"执行完就算完成"。

### 6. 文档是跨会话的唯一记忆

Agent 没有长期记忆（Claude Code 的 memory 系统除外，但那更适合记用户偏好，不适合记项目状态）。上一次对话中 Agent 知道的所有事情，在下一次对话中全部丢失。唯一能跨会话传递信息的载体就是**仓库里的文件**。

代码改了但文档没跟上 → 下一次对话的 Agent 读到过时文档 → 基于错误信息做决策 → 产生连锁错误。

因此需要**完工检查清单**来机械化地保证文档同步。这不是建议，是硬约束——每次任务结束都必须走完清单，就像飞行员的起飞检查清单一样。

### 7. CHANGELOG 是高频写入的文件，必须脚本化操作

CHANGELOG 会随项目推进不断增长，可能达到几百甚至上千行。如果 Agent 每次写日志前都读取全文，会浪费大量上下文空间。更危险的是，Agent 可能在错误的位置插入条目，破坏倒序结构。

因此 CHANGELOG 有一套专门的脚本操作规则（详见 AGENTS.md 模板中的"CHANGELOG 规则"部分），核心是：**不读全文，通过 `scripts/changelog.py` 查看标题树、读取局部内容或追加条目。** 这把高频重复动作从上下文里挪到工具里，同时保留 Agent 对内容取舍的判断空间。当前任务状态不进入 CHANGELOG，由 `docs/CURRENT.md` 承担。

### 8. Occam 与 Bitter Lesson 是防止治理系统自增殖的护栏

初始化文档体系很容易走向"看起来更完整，实际上更重"：多加一个目录、多写一份规则、多列一个任务识别表，短期让 Agent 感觉更有把握，长期却会制造冷启动成本、一致性维护成本和规则漂移。

因此本 skill 将两条原则作为通用工程判断准则：

- **Occam's Razor**：如无必要，勿增实体。新增文件、脚本、字段、规则或流程前，必须能说清它解决的具体问题；如果只是让体系看起来完整，应拒绝。
- **Bitter Lesson**（源自 Rich Sutton，2019）：通用方法优于硬编码先验。长期来看，利用通用能力（模型理解、语义检索、结构化工具）比嵌入人类知识（关键词规则、任务模式枚举、提前分类）更有效。短期看，硬编码规则能让 Agent 快速上手；但长期看，它们会制造维护负担、抑制灵活性，最终成为演进障碍。优先设计能随计算/数据增长而自动扩展的元方法，而非预设具体场景的静态规则。

**两者的边界同样重要**：Occam 不反对必要复杂性，Bitter Lesson 也不反对结构性先验。硬链接脚本、CHANGELOG 脚本、计划文件这些结构之所以成立，是因为它们承载了可验证、重复发生、会消耗上下文的机械动作；相反，为每种未来任务预设规则表，就应先被这两条原则拦住。

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

AGENTS.md、CLAUDE.md、GEMINI.md 必须保持内容一致（因为不同 Agent 框架加载不同入口文件）。常见的错误是：

1. Agent 修改了 AGENTS.md，但忘记运行 `scripts/agent_links.py` 同步
2. Agent 直接修改了 CLAUDE.md 或 GEMINI.md（这是错误的）
3. 硬链接因编辑器行为而断链

**解决方案：Git pre-commit hook 强制检查**

在 `.githooks/pre-commit` 中添加检查逻辑：

```bash
#!/bin/bash
# 检查 AGENTS.md、CLAUDE.md、GEMINI.md 是否一致
AGENTS_MD5=$(md5sum AGENTS.md | cut -d' ' -f1)
CLAUDE_MD5=$(md5sum CLAUDE.md | cut -d' ' -f1)
GEMINI_MD5=$(md5sum GEMINI.md | cut -d' ' -f1)

if [ "$AGENTS_MD5" != "$CLAUDE_MD5" ] || [ "$AGENTS_MD5" != "$GEMINI_MD5" ]; then
    echo "⚠️  AGENTS.md、CLAUDE.md、GEMINI.md 不一致"
    echo "请运行：python scripts/agent_links.py repair"
    exit 1
fi
```

配置 Git 使用仓库内的 hooks 目录：

```bash
git config core.hooksPath .githooks
```

这样每次 commit 时都会自动检查，如果不一致会拒绝提交并提示正确的修复流程。这是真正的**硬约束**，Agent 无法绕过。

---

## 目标文件结构

执行本 skill 后，**目标项目**应具备以下结构：

```
目标项目/
├── AGENTS.md              # 主文件（行为规则 + 导航）
├── CLAUDE.md              # → AGENTS.md 的硬链接
├── GEMINI.md              # → AGENTS.md 的硬链接
├── STRUCTURE.md           # 文档总索引（一张导航表）
├── CHANGELOG.md           # 变更记录（倒序，最新在前）
├── scripts/
│   ├── changelog.py       # CHANGELOG 的 token-light 操作入口
│   └── agent_links.py     # AGENTS/CLAUDE/GEMINI 硬链接检查与修复
├── .githooks/             # （可选）质量门控
│   └── pre-commit
└── docs/
    ├── CURRENT.md         # 当前任务状态（单 owner handoff / 全局入口）
    ├── overview.md        # 系统主线与设计决策
    ├── api.md             # API 约定（如有 API 的项目）
    ├── deployment.md      # 部署与环境配置
    ├── pitfalls.md        # 已知环境陷阱
    └── plans/
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
    │   ├── zh/                       # 中文模板集
    │   └── en/                       # 英文模板集
    │       （AGENTS, STRUCTURE, CURRENT, overview, api, deployment,
    │        pitfalls, plan, CHANGELOG — 共 9 个 .tpl 文件）
    ├── scripts/
    │   ├── changelog.py              # CHANGELOG 标题树 / 局部读取 / 追加
    │   └── agent_links.py            # AGENTS/CLAUDE/GEMINI 硬链接检查与修复
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

不要把这一阶段当成"机械回答 7 个问题"。更好的做法是采用 **intent-first / deep-interview** 思路：通过读代码、读 README、查看现有文档、必要时向用户追问，逐步澄清项目画像；**当你已经掌握足够信息，能够可靠地填写模板时，才进入第 1 步**。

至少澄清以下维度：

1. **项目做什么？**（一句话概括，这决定了 overview.md 的开头）
2. **技术栈是什么？**（语言、框架、前后端分离？这影响代码风格约定和 pre-commit 片段选择）
3. **有哪些硬约束？**（密钥管理、构建产物路径、特殊部署方式、合规要求）
4. **当前有没有已存在的文档？** 需要迁移还是从零开始？如果已有文档，哪些内容值得保留？（决定是否要走第 3 步的迁移流程）
5. **项目使用哪些 AI Agent？**（Claude Code、Codex、Gemini CLI、Cursor 等——这决定需要哪些硬链接文件名）
6. **项目的构建产物在哪里？**（dist/、build/、data/、node_modules/ 等——这些路径需要写入硬约束）
7. **项目有没有自动化测试？** 测试命令是什么？这决定了测试要求部分怎么写。
8. **这个项目的默认协作倾向是什么？**（通常是单 Agent 顺序推进，还是经常多 Agent / 多窗口并行？这是默认倾向，不是对每个任务的一刀切规定）
9. **这个项目更常见的是哪类任务？**（小修改、分阶段任务，还是需要 reviewer / verifier 的高风险改动？）
10. **文档语言？**（中文 / 英文 / 其他——决定使用 `assets/templates/zh/` 还是 `assets/templates/en/`）

在落文档前，先根据项目的默认倾向写出协作偏好；**具体到每个任务开始前，再显式选择一种工作模式**：

- **直接执行模式**：小任务、低风险修改，不建详细计划；`docs/CURRENT.md` 写 1-3 行即可。
- **分阶段模式**：中等复杂度任务，需要计划文件，但通常仍是单 owner 顺序推进。
- **协作模式**：高复杂度或高风险任务，存在多 Agent / 多窗口并行，计划文件中必须包含任务分配、领取状态和复查节点。

如果用户没有明确说明，默认从轻量模式开始；一旦任务跨模块、跨会话或需要并行，就升级到更重的模式。**不要在初始化阶段把某个模式永久写死给整个项目**。

**把 intent 结果落盘。** 第 0 步收集的信息不要只留在对话里——初始化完成后，它就是这份文档体系的"出生档案"。建议第 5 步结束时把 10 个维度的答案写入 `docs/plans/completed/initialization.md`，将来审计或重构文档体系时就有据可查。

### 第 1 步：创建 AGENTS.md 及硬链接组

1. 选择模板语言：
   - 中文项目：读 `assets/templates/zh/AGENTS.md.tpl`
   - 英文项目：读 `assets/templates/en/AGENTS.md.tpl`
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

5. 写入目标项目的 `AGENTS.md` 后，用脚本创建硬链接并验证：

   ```bash
   python scripts/agent_links.py repair
   python scripts/agent_links.py check
   ```

6. 如果检查失败，先确认 `CLAUDE.md` / `GEMINI.md` 是否含有不同内容；确认可以用 `AGENTS.md` 覆盖后再修复：

   ```bash
   python scripts/agent_links.py repair
   # 内容不同且已人工确认时才使用：
   python scripts/agent_links.py repair --force
   ```

**关于"硬链接不可用"的 fallback**：某些文件系统（WSL 跨盘、ReFS、exFAT、部分 CI 容器）不支持硬链接。此时不要偷偷改成三份手工维护；应在 AGENTS.md 中明确降级策略，例如"只编辑 AGENTS.md，另两个文件由脚本复制同步"，并扩展 `scripts/agent_links.py` 来承载这种策略。

**关于编辑器断链**：部分编辑器用"写临时文件 → 删原文件 → 重命名"保存，会创建新 inode 从而断开硬链接。建议在第 6 步配置 pre-commit，让每次提交时自动重建。

### 第 2 步：创建 STRUCTURE.md 和 docs/ 目录

按同样的模板机制生成以下文件（从 `assets/templates/{zh,en}/` 对应 .tpl 读，填充后写入目标项目）：

| 目标路径 | 模板 |
|---------|------|
| `STRUCTURE.md` | `STRUCTURE.md.tpl` |
| `docs/CURRENT.md` | `CURRENT.md.tpl` |
| `docs/overview.md` | `overview.md.tpl` |
| `docs/api.md`（可选） | `api.md.tpl` |
| `docs/deployment.md` | `deployment.md.tpl` |
| `docs/pitfalls.md`（可选） | `pitfalls.md.tpl` |
| `CHANGELOG.md` | `CHANGELOG.md.tpl` |

然后建立计划目录：

```bash
mkdir -p docs/plans/active docs/plans/completed
touch docs/plans/active/.gitkeep docs/plans/completed/.gitkeep
```

**不要留空文件**——至少写一个标题 + 一句话说明文件的定位，否则 Agent 不知道该往里写什么。模板本身已经满足这个要求，只要别把模板里的指导注释全删光就行。

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

3. **去重**：如果一条信息在多份旧文档里都出现，只保留一份；如果和新模板里已经写好的内容冲突（比如模板的"文档维护原则"），以新结构为准。
4. **标注废弃**：旧文档如果整体被拆分迁移，在顶部加一条"**⚠️ 本文件的内容已迁移至 docs/ 及 AGENTS.md。保留此文件仅供历史追溯，后续更新请前往对应新位置。**"——不要立刻删除，让 git blame / PR 评论等历史引用还能找到。
5. **记录到 CHANGELOG**：用 `python scripts/changelog.py add ...` 把本次迁移作为一次独立变更记录。

### 第 4 步：初始化首个计划文件（可选）

如果用户的下一个任务已经明确、且是分阶段或协作模式，就基于 `assets/templates/{zh,en}/plan.md.tpl` 在 `docs/plans/active/` 下创建第一份计划，顺便校验这个模板在具体任务上好不好用。

如果当前没有待启动的任务，跳过本步骤——计划应该按需创建，而不是放空壳进去。

### 第 5 步：记录初始化本身

把第 0 步收集到的 intent 答案写入 `docs/plans/completed/initialization.md`（用 `plan.md.tpl` 作骨架，状态直接标 `✅ completed`）。这一步有两个作用：
- 将来重新审视文档体系时，可以对照出生档案看哪些假设已变
- 给未来的 Agent 一个具体范例：计划文件长什么样、怎么填

同时用脚本写入 CHANGELOG，不要手工打开全文：

```bash
python scripts/changelog.py add \
  --title "初始化文档体系" \
  --body "建立 agent-first 文档结构：AGENTS.md（含硬链接 CLAUDE.md / GEMINI.md）+ STRUCTURE.md + docs/ 层级；配置 scripts/changelog.py 与 scripts/agent_links.py，脚本化维护日志和硬链接；迁移/整合旧文档（如适用）：见 docs/plans/completed/initialization.md"
```

### 第 6 步：初始化质量门控

**强烈推荐执行，不要因为"只是文档"就跳过**——能用工具强制的规则就不要只靠文档（设计哲学第 9 条）。

1. 确认脚本已经复制到项目：

   ```bash
   python scripts/changelog.py titles --limit 3
   python scripts/agent_links.py check
   ```

2. **配置 AGENTS.md 同步检查（必须）**：

   这是防止 Agent 修改 AGENTS.md 后忘记同步的关键保护。创建 `.githooks/pre-commit` 文件：

   ```bash
   cat > .githooks/pre-commit << 'EOF'
   #!/bin/bash
   # 检查 AGENTS.md、CLAUDE.md、GEMINI.md 是否一致

   # 计算 MD5（兼容 Linux 和 Windows Git Bash）
   if command -v md5sum &> /dev/null; then
       AGENTS_MD5=$(md5sum AGENTS.md | cut -d' ' -f1)
       CLAUDE_MD5=$(md5sum CLAUDE.md | cut -d' ' -f1)
       GEMINI_MD5=$(md5sum GEMINI.md | cut -d' ' -f1)
   elif command -v md5 &> /dev/null; then
       AGENTS_MD5=$(md5 -q AGENTS.md)
       CLAUDE_MD5=$(md5 -q CLAUDE.md)
       GEMINI_MD5=$(md5 -q GEMINI.md)
   else
       echo "⚠️  警告：无法计算 MD5（未找到 md5sum 或 md5 命令）"
       exit 0
   fi

   # 比较三个文件的 MD5
   if [ "$AGENTS_MD5" != "$CLAUDE_MD5" ] || [ "$AGENTS_MD5" != "$GEMINI_MD5" ]; then
       echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
       echo "⚠️  Git commit 被拒绝"
       echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
       echo ""
       echo "AGENTS.md、CLAUDE.md、GEMINI.md 三个文件的内容不一致。"
       echo ""
       echo "这可能是因为："
       echo "  1. 你修改了 AGENTS.md 但忘记运行同步脚本"
       echo "  2. 你直接修改了 CLAUDE.md 或 GEMINI.md（这是错误的）"
       echo ""
       echo "正确的流程："
       echo "  1. 编辑 AGENTS.md（不要编辑 CLAUDE.md 或 GEMINI.md）"
       echo "  2. 运行：python scripts/agent_links.py repair"
       echo "  3. 再次提交"
       echo ""
       echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
       exit 1
   fi

   exit 0
   EOF
   chmod +x .githooks/pre-commit
   git config core.hooksPath .githooks
   ```

   这会在每次 commit 前自动检查三文件是否一致，如果不一致会拒绝提交并提示正确的修复流程。

3. 按项目技术栈选择其他 pre-commit 检查（可选）：

   - Python 项目 → `assets/hooks/pre-commit-python.sh`
   - Node/TS 项目 → `assets/hooks/pre-commit-node.sh`
   - Go 项目 → `assets/hooks/pre-commit-go.sh`
   - 混合 / 特殊栈 → `assets/hooks/pre-commit-generic.sh`（自行补 lint 命令）
   - 已在用 pre-commit 框架 → `assets/hooks/pre-commit-config.yaml` 贴到项目根的 `.pre-commit-config.yaml`

   将选中的脚本内容**追加**到 `.githooks/pre-commit` 文件末尾（不要覆盖第 2 步创建的同步检查）。

4. 本地触发一次确认能通过：

   ```bash
   # 测试 AGENTS.md 同步检查
   echo "# test" >> CLAUDE.md && git add CLAUDE.md && git commit -m "test: hook"
   # 应该被拒绝，然后修复：
   git checkout -- CLAUDE.md
   
   # 正常提交测试
   echo "" >> AGENTS.md && git add AGENTS.md && python scripts/agent_links.py repair && git commit -m "test: hook pass"
   git reset HEAD~1   # 不留垃圾提交
   ```

### 第 7 步：静态自检

1. 所有文件已创建且路径正确
2. `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 硬链接一致（`python scripts/agent_links.py check` 返回 0）
3. `AGENTS.md` 中的所有链接指向真实存在的文件
4. `STRUCTURE.md` 中的索引表与 `docs/` 下的文件一一对应
5. `docs/CURRENT.md` 已创建，并在 `AGENTS.md` 的信息导航中可访问
6. `CHANGELOG.md` 可由 `python scripts/changelog.py titles --limit 5` 输出标题树
7. `AGENTS.md` 行数不超过约 150 行（超出说明有内容该下沉到 docs/）

### 第 8 步：reviewer-perspective 自检（推荐）

这一步是对设计哲学第 5 条的兑现——**不要让"执行者自检"冒充"已验证"。** 文档初始化本身就是中等风险的工作：一旦写得不清楚、AGENTS.md 里的规则模糊、导航指针断链，后面几十次对话都会带着病上路。

建议做法：

1. **新开一个 Agent 窗口或启动 subagent**：
   - 新窗口：打开新的 Claude Code 窗口或新会话
   - Subagent：使用 Agent 工具启动子 agent（如 code-reviewer）
2. 让它**只读 AGENTS.md**，不看其他文件，然后回答：
   - 这个项目做什么？
   - 我不能改哪些文件？
   - 任务完成时我需要做什么？
   - 如果接到一个复杂任务，我应该先去哪里？
3. 如果回答含糊或错误，说明 AGENTS.md 没写清楚——回去改，直到新上下文能通过这个测试为止

这个测试的成本很低（十几分钟），但收益极高：它验证的恰恰是 AGENTS.md 作为"入口地图"最核心的功能。

初始化完成后，把第 0 步回答 + 自检结果追加到 `docs/plans/completed/initialization.md` 的"完成记录"里。

---

## 执行计划模板与跨上下文工作流

执行计划不只是"待办事项列表"，它是**上下文窗口之间、以及多个协作角色之间的交接协议**。

---

### 问题背景

Agent 的上下文窗口是有限的。一个复杂任务（如"重构认证系统"）可能需要修改 20+ 个文件，涉及多个子系统，不可能在一个上下文窗口里完成。

**关键约束：后进入的 Agent 对前面发生的事情一无所知。** 它唯一能获取信息的渠道就是：
- 计划文件中的进度记录
- 代码的当前状态（git diff / git log）
- docs/ 中的文档更新

因此，计划文件必须足够完整，让一个"失忆"的 Agent 能快速接手。

---

### 工作模式一：单 Agent 跨上下文工作流

适用场景：中等复杂度任务，需要多个会话窗口按顺序执行。

**工作流程：**

1. **制定计划**：人类让 Agent 制定详细计划，写入 `docs/plans/active/任务名.md`
2. **执行阶段 1**：人类告诉 Agent "先执行阶段 1"
3. **阶段 1 完成**：Agent 执行阶段 1，上下文逐渐填满
4. **交接**：
   - Agent 更新计划文件：阶段 1 状态改为 `✅ completed`，填写完成记录
   - Agent 提交代码：确保改动已 commit
5. **新窗口继续**：
   - 人类**开新的 Agent 窗口**（或新会话）
   - 告诉新 Agent："继续执行计划，见 `docs/plans/active/任务名.md`"
   - 新 Agent 读取计划文件，看到阶段 1 已完成，继续阶段 2
6. **重复**直到所有阶段完成

**关键点：**
- 每个阶段结束后必须更新计划文件并 commit
- 新窗口启动时，第一件事就是读取计划文件
- 阶段粒度要合理（5-10 个文件），确保一个窗口能完成

---

### 工作模式二：多 Agent 并行协作工作流

适用场景：高复杂度或高风险任务，需要多个 Agent/窗口并行推进，或需要独立 reviewer。

**角色分工：**

| 角色 | 职责 |
|------|------|
| **Coordinator** | 拆解任务、分配 owner/reviewer、维护任务分配表、汇总结果 |
| **Owner** | 领取任务、执行实现、提交代码、更新计划状态 |
| **Reviewer** | 在新上下文中复查代码、验证通过后将任务标记为完成 |

**工作流程：**

1. **任务拆解**：
   - 协调人分析任务，拆分为多个可并行的子任务或阶段
   - 为每个子任务分配 owner 和 reviewer
   - 将任务分配表写入计划文件

2. **并行执行**：
   - 不同 owner 在各自的窗口中领取任务（状态从 `queue` 改为 `in_progress`）
   - **（推荐）使用 git worktree 为每个 owner 创建独立工作环境**，避免多 Agent 同时修改同一分支产生冲突，详见下方"工具支持：Git Worktree"
   - 各自推进、验证、提交代码
   - 完成后更新计划：状态改为 `review`，填写完成记录

3. **交叉复查**：
   - reviewer 在**新的上下文**中复查代码
   - 如有问题，退回 `in_progress` 并明确返工原因
   - 通过后改为 `✅ completed`

4. **汇总收尾**：
   - 协调人确认所有子任务进入 `✅ completed`
   - 汇总结果、确认风险已记录
   - 将计划移至 `docs/plans/completed/`
   - 推动 CHANGELOG 与架构文档同步

**关键点：**
- **不要让多个 owner 共享一个模糊的"当前状态"**：每个任务都要有明确的 owner
- **能独立提交和复查的任务才适合并行**：强耦合修改宁可顺序推进
- **交接摘要必须完整**：写成"另一个上下文完全没见过这段工作也能接手"的粒度
- **Owner 发现分配问题时**：如果任务粒度、依赖关系或技术方案不合理，应上报 Coordinator 重新拆解和分配，而不是私下转包给 subagent 或强行执行。这符合 Bitter Lesson 原则——依赖协调机制这个通用方法，而非硬编码"禁止/允许"的静态规则。
- **CURRENT.md 的作用**：多 Agent 并行时，不要把 CURRENT.md 当成唯一真相源；计划文件才是任务分配和状态流转的核心，CURRENT.md 只保留全局摘要或入口指针

---

### 工具支持：Git Worktree

在多 Agent 并行协作时，**推荐使用 git worktree** 来隔离不同 owner 的工作环境。

**什么是 git worktree？**

Git worktree 允许你在同一个仓库的不同目录下检出不同的分支，这些工作目录共享同一个 `.git` 仓库，但各自有独立的工作区。

**为什么需要 git worktree？**

多个 Agent 同时修改同一个分支会产生冲突和混乱。git worktree 让每个 owner 在自己的分支上工作，通过 PR/MR 合并，避免了这些问题。

**使用示例：**

```bash
# 1. 主分支是 main，当前在项目根目录工作
# 2. 为 owner A 创建一个 worktree
git worktree add ../project-owner-a feature/owner-a-task

# 3. 为 owner B 创建另一个 worktree
git worktree add ../project-owner-b feature/owner-b-task

# 4. 每个 owner 在自己的目录中工作
# owner A 在 ../project-owner-a
# owner B 在 ../project-owner-b

# 5. 查看所有 worktree
git worktree list

# 6. owner 完成任务后，删除 worktree（可选）
git worktree remove ../project-owner-a
```

**与 Agent 的配合使用：**

1. **协调人创建 worktree**：
   ```bash
   # 为每个子任务创建独立分支和 worktree
   git worktree add ../project-auth refactor/auth
   git worktree add ../project-payment refactor/payment
   ```

2. **分配 worktree 给 owner**：
   - 告诉 owner A："在 `../project-auth` 目录下工作，这是你的独立环境"
   - 告诉 owner B："在 `../project-payment` 目录下工作"

3. **owner 在各自 worktree 中工作**：
   - 独立修改、提交代码
   - 互不干扰，不会产生冲突

4. **合并代码**：
   - owner 完成后，创建 PR/MR 合并到主分支
   - reviewer 代码审查通过后合并
   - 删除 worktree（可选）

**git worktree 的优势：**

| 优势 | 说明 |
|------|------|
| **隔离性** | 每个 owner 有独立的工作目录，互不干扰 |
| **共享 Git 历史** | 所有 worktree 共享同一个 `.git`，节省空间 |
| **独立分支** | 每个任务在不同分支上，便于代码审查和回滚 |
| **无冲突** | 不会因为同时修改同一文件而产生冲突 |
| **易于清理** | 任务完成后可删除 worktree，保持工作区整洁 |

**注意事项：**

- worktree 路径建议放在项目根目录的父目录下（如 `../project-xxx`），避免混入项目本身的文件结构
- 每个 worktree 应该有明确的命名（如 `../project-auth`、`../project-payment`），便于识别
- 协调人需要用 `git worktree list` 定期检查活跃的 worktree，避免遗留过多未清理的工作目录

**不使用 git worktree 的风险：**

多个 Agent 在同一个分支上工作会导致：
- 同时修改同一文件产生冲突
- 未完成的代码影响其他 owner
- 难以追溯谁改了什么
- 代码审查困难

---

### 两种模式的对比

| 维度 | 单 Agent 跨上下文 | 多 Agent 并行协作 |
|------|-----------------|-------------------|
| **适用场景** | 中等复杂度、顺序执行 | 高复杂度/高风险、可并行 |
| **计划复杂度** | 阶段划分即可 | 需要任务分配表 + 状态流转 |
| **Owner 数量** | 1 个（顺序推进） | 多个（并行推进，可用 git worktree 隔离） |
| **验证方式** | 自检或可选 reviewer | 每个 task 必须有 reviewer |
| **CURRENT.md** | 可作为轻量交接协议 | 只保留全局摘要，不作为唯一真相源 |
| **风险** | 上下文用完需中断 | 需要协调人避免冲突 |

详见下方"计划文件结构"和"模式选择与裁剪指南"。

### 计划文件结构

计划模板在 `assets/templates/{zh,en}/plan.md.tpl`。关键字段：

- **任务分配表**：谁领什么、状态到哪（`queue` / `claimed` / `in_progress` / `review` / `✅ completed`）
- **阶段划分**：每阶段的目标、涉及文件、验证标准、owner、reviewer、完成记录、交接摘要
- **决策记录**：执行中做出的关键选择，带日期和原因
- **风险与遗留**

### 阶段粒度控制指南

阶段粒度是计划成败的关键。太大了一个窗口做不完，太小了切换开销大。

**经验法则：**
- 一个阶段涉及 **5-10 个文件**的修改是比较合适的
- 如果一个阶段的描述需要超过 10 行才能说清楚，考虑拆分
- 每个阶段结束后系统必须能正常运行（不能出现"改了一半"的状态）

**常见的阶段拆分方式：**
- 按层拆分：先改数据层 → 再改业务层 → 最后改 UI 层
- 按功能拆分：先实现核心路径 → 再加错误处理 → 最后补边界情况
- 按风险拆分：先做最有可能出问题的部分 → 确认方向正确 → 再铺开

**并行协作时的额外规则：**
- 不要让多个 owner 共享一个模糊的"当前状态"；每个任务都要有明确的 owner
- 能独立提交和复查的任务才适合并行；强耦合修改宁可顺序推进
- 阶段交接摘要必须写成"另一个上下文完全没见过这段工作也能接手"的粒度

### Agent 在每个阶段完成时应该做的事

在 AGENTS.md 的完工检查清单之外，执行计划中的阶段完成时还需要：

1. **更新计划文件**：把当前阶段状态从 `in_progress` 推进到 `review` 或 `✅ completed`，并填写"完成记录"
2. **记录偏离**：如果实际执行和计划有出入（几乎一定会有），记在"决策记录"中
3. **触发验证/复查**：至少完成自检；高风险任务优先交给新的 reviewer 视角检查，再从 `review` 改为 `✅ completed`
4. **检查下一阶段的前置条件**：确认当前状态满足下一阶段的启动条件
5. **提交代码**：确保当前阶段的改动已经 commit，这样下一个窗口的 Agent 能通过 git log 看到

### 协调人应该做什么

如果计划中存在协调人，这个角色至少负责：

1. 在任务开始时拆解阶段、分配 owner 和 reviewer
2. 在执行过程中维护任务分配表，避免重复领取和状态漂移
3. 在 review 未通过时把任务退回 `in_progress`，并明确返工原因
4. 在所有阶段进入 `✅ completed` 后汇总结果、确认风险已记录
5. 把计划从 `docs/plans/active/` 移到 `docs/plans/completed/`，并推动 CHANGELOG 与架构文档同步；写 CHANGELOG 时用 `scripts/changelog.py`

### 计划完成后的收尾

1. 把计划文件从 `docs/plans/active/` 移到 `docs/plans/completed/`
2. 用 `python scripts/changelog.py add ...` 更新 CHANGELOG，记录这个计划的完成
3. 如果计划过程中产生了新的设计决策，确保已同步到 `docs/overview.md`

---

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

对于小型项目，可以把 overview.md 的内容直接放在 AGENTS.md 的信息导航区域下方（只要 AGENTS.md 不超过 100 行）。但一旦项目开始增长，就应该及时拆分。

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

11. **全靠软约束**：所有规则都写在 AGENTS.md 里，没有任何机械化验证。Agent 可能遗忘或违反规则，尤其在长上下文中。解法：能用 hook/lint/CI 强制的规则，编码为工具（第 6 步）。具体到 AGENTS.md 同步问题：

   - **症状**：Agent 修改 AGENTS.md 后忘记同步到 CLAUDE.md/GEMINI.md，导致三文件内容不一致
   - **后果**：下次对话时，不同 Agent 框架加载的入口文件内容不同，产生行为差异
   - **软约束**：在 AGENTS.md 开头写"修改后请运行同步脚本"——Agent 会忘记或忽略
   - **硬约束**：在 `.githooks/pre-commit` 中检查三文件 MD5，不一致则拒绝提交（第 6 步第 2 点）
   - **效果**：Agent 无法绕过，commit 时自动被拦截并提示正确的修复流程

12. **关键原则只存在于对话中**：在某个对话中讨论并确认了"硬约束优先"原则，但没有写入 AGENTS.md 或其他文档。新对话开始时，Agent 完全不知道这个原则的存在。解法：重要的原则和决策必须写入文档（AGENTS.md 的准则段），这样每次新对话都会自动加载。

12. **初始化完就不自检**：AGENTS.md 写完自己读一遍觉得没问题就结束。但执行者在同一上下文里天然有确认偏误。解法：第 8 步的 reviewer-perspective 自检——让一个新上下文只看 AGENTS.md 回答几个关键问题。

13. **为了完整感复制治理形式**：看到多层规则、完整组织隐喻或复杂流程，就照搬到新仓库。解法：只保留能解决真实问题的原则和结构；具体形式必须由目标项目的实际约束长出来。

14. **迁移时直接删旧文档**：历史引用瞬间失效。解法：第 3 步先标"已迁移"，保留一段时间再彻底删除。
