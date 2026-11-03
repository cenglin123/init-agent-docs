# init-agent-docs — skill maintainer notes

此 README 面向**维护本 skill 的人或 agent**（不是执行 skill 的 agent）。执行指令请看 [SKILL.md](SKILL.md)。

## 这个 skill 做什么

为一个代码仓库初始化"面向 AI agent 协作"的文档体系：

- `AGENTS.md`：唯一入口——行为规则 + 信息导航 + profile 对应文件治理指针（Agent 面向；实际加载由宿主配置决定，不生成 CLAUDE.md / GEMINI.md 副本）
- `README.md`：项目概述、快速开始、贡献指南（人类面向；从模板生成或迁移保留）
- `docs/STRUCTURE.md`：中大型文档总索引与详细文件治理规则
- `docs/governance.md`：中大型自维护与规则改进合同；Small 从同一源合同投影内联 AGENTS
- `docs/CHANGELOG.md`：倒序变更记录
- `scripts/changelog.py`：CHANGELOG 标题树、近期条目、局部读取和追加
- `scripts/audit.py`：文档一致性深度审计（死链 / 结构完整性 / 依赖漂移 / 记忆结构，定期跑 ~15 项）
- `scripts/check_all.py`：高频完工检查器——无输出=通过，FAIL 自带修复指引（每次任务后跑 ~4 项）
- `scripts/maintain.py`：文档体系自动化维护管线（中型+项目）——重建 MEMORY.md 索引标记段（覆盖记忆条目 + bugfix 文档）+ 调用 audit 机械检查 + 记忆活性统计 + 近期脉络摘要；`--check` 为只读校验
- `assets/plugins/governance-watch.js`：治理可发现性插件（opencode，可选）——会话边界检测治理目录脏区，在入口 AGENTS.md 写入显眼提醒行（见可选集成的会话级治理提醒）
- `docs/{overview,api,deployment,pitfalls,CURRENT,audit-checklist,frontmatter-schemas}.md`：专题文档（中型 / 大型项目；Small 文档为 `CURRENT.md`、`CHANGELOG.md`、`audit-checklist.md`、`initialization.md`，另有根 AGENTS/README 和三个文档脚本）
- `docs/plans/{active,completed}/`：执行计划目录（中型及以上才创建；小型项目用 `docs/initialization.md` 作为出生档案）
- `.agents/memory/`：跨会话记忆系统（中型+项目），含 MEMORY.md 索引 + user/ 子目录
- `.githooks/`：可选 lint 质量门控（内置记忆结构兜底与治理文档修改提醒）
- `scripts/worktree_task.py`：可选的任务 worktree 与协作入场工具（按需读取 optional-integrations.md）；canonical 分支快进保护 hook 可另行选装，入场协调不依赖 hook

设计取舍见 assets/references/design-principles.md，执行阶段见 assets/references/initialization.md。

协作分工由 Agent 按任务选择；保留所有权、交接与独立验收，已选控制器继续掌握预算/终端裁决，无控制器用本地合同完成，不建立平行组织。

## 目录结构

```
init-agent-docs/
├── SKILL.md                              # 主指令（执行 skill 的 agent 读这个）
├── README.md                             # 你现在读的这份文件
└── assets/
    ├── templates/
    │   └── zh/                           # 中文模板集（15 个 .tpl）
    ├── scripts/
    │   ├── changelog.py                  # CHANGELOG 脚本化维护
    │   ├── maintain.py                   # 维护管线：记忆+bugfix 索引重建 + 审计 + 活性报告（中型+）
    │   ├── worktree_task.py              # 任务 worktree 与协作入场工具（可选）
    │   ├── audit.py                      # 深度审计（定期）
    │   └── check_all.py                # 高频完工检查（每次任务后）
    ├── hooks/
    │   ├── pre-commit-python.sh          # ruff / flake8
    │   ├── pre-commit-node.sh            # eslint / prettier
    │   ├── pre-commit-go.sh              # gofmt / go vet
    │   ├── pre-commit-generic.sh         # 空壳，自己填
    │   ├── reference-transaction.sh      # canonical 分支快进保护（可选，配 worktree_task）
    │   └── pre-commit-config.yaml        # 给使用 pre-commit 框架的项目
    └── pitch/
        └── presentation.html             # 对外分享用的 pitch deck，不是运行时产物
```

目标项目结构（中型项目，含记忆系统）：

```
目标项目/
├── AGENTS.md              # 唯一入口：行为规则 + 治理指针 + 内联记忆 + 导航
├── .agents/memory/        # 跨会话记忆（硬约束内联在 AGENTS.md）
│   ├── MEMORY.md          # 记忆索引（标记段由 maintain.py 自动重建，禁止手改）
│   └── user/role.md       # 用户画像
├── docs/
│   ├── STRUCTURE.md       # 文档总索引
│   ├── CHANGELOG.md       # 变更记录
│   ├── CURRENT.md         # 当前任务状态
│   ├── overview.md        # 系统主线
│   └── ...
└── scripts/
    ├── changelog.py
    ├── maintain.py
    ├── audit.py
    └── check_all.py
```

## 模板占位符约定

模板里使用两种占位形式：

- `[方括号]`：给执行 agent 看的"此处替换为具体值"（如 `[项目名]`、`[今天的日期]`）
- `<!-- HTML 注释 -->`：给执行 agent 看的填写指导，生成最终文件时应替换为实际内容或整段删除

**不用 `{{mustache}}` 风格的原因**：这些占位符需要 agent 根据项目上下文灵活填写，不是机械字符串替换；用人类可读的方式描述"这里应该写什么"比变量名更有用。

## 已知限制

1. **遗留三文件项目**：旧版本初始化的项目若仍有 `CLAUDE.md` / `GEMINI.md` 同步副本和 `scripts/agent_links.py`，重新执行本 skill 时会整合内容进 AGENTS.md 并删除副本与同步脚本；旧 hook 中的同步检查一并移除。
2. **模板仅一种语言**：当前只附带 zh/。其他语言需要手工复制 zh 目录并翻译；`scripts/changelog.py` 内置了对英文 CHANGELOG 标题的识别，所以即使模板只有中文，用户后续手写英文条目仍能正确归类。
3. **pre-commit 片段没跑过所有平台**：Windows 原生 Git Bash 下 `xargs` 对空输入的处理偶有差异；如遇问题，用 `if [ -n "$STAGED" ]; then echo "$STAGED" | ...; fi` 兜住。

## 维护入口

维护本仓先读 [AGENTS.md](AGENTS.md)。规则等级与标定归 [设计原则](assets/references/design-principles.md)，日常维护与规则候选归 [治理合同](assets/references/governance-contract.md)。本文件保留面向维护者的产品说明与评测方法。

验证使用 `python -X utf8 -m pytest tests/ -q`、`python -X utf8 scripts/check_source.py` 与 `git diff --check`；模板改动在实际测试项目运行初始化和独立入口验收。来源检查只复用 audit.py 的 R2 判据，不执行目标全套审计；交付脚本安装到目标项目验证。

### 评测义务

本仓自身的行为面改动——`AGENTS.md`、`SKILL.md`、`README.md`、`assets/templates/zh/**`、`assets/references/*.md`（不含评测方法 `eval-baseline.md`）——提交前按评测方法运行适用 L1 清单，在[结果账本 evals/results.md](evals/results.md)记分。方法与结果均不因自身修订制造记分义务。义务分工：

- **记分粒度**：允许范围化记分（`L1 partial: scope=…`，scope 须枚举实际触达的 test bed 维度，skipped 维度计入噪音率）与多条改动批量补记。`assets/scripts/**`、`assets/hooks/**`、`.githooks/**`、`assets/plugins/**` 由 pytest 门控，不改变 skill 产出质量，不入 eval 义务。
- **L2/L3 判分**不由执行者自跑自记：由维护者发起 converge 评议承担（跨模型族独立判分），结果记入回归记录表。
- **唯一结果入口**：[评测方法](assets/references/eval-baseline.md)定义方法与标准，[结果账本 evals/results.md](evals/results.md)保存来源评测结果，不复制下游。审计裁决与行为面记分各记其实际结论；生成项目以实际验证证据为默认，明确使用重放时才启用 eval 字段，R1 校验显式记录完整性。
- **R2 强制机制**（audit.py）：anchor = 最近一次触碰结果账本记分行的提交，兼容迁移前历史锚点，方法文字不重置锚点；其后 1 个行为面提交 → warn（放行补记），≥2 → error（阻塞）。来源命令与 pre-commit 复用该实现；hook 纳入暂存记分行，记分与行为改动同一提交可自锚定。R2 是 fixture 重放 runner 落地前的过渡机制，runner 使记分连续化后退役；支持 `.git` 指针文件的 linked worktree。

## 吸纳外部素材

仅吸纳跨项目可迁移、解决实际痛点且能改变指令行为的素材；先查现有规则，同义方法归并，新增判断步骤或失败模式才新增实体。素材本身不设收件箱或永久台账，论证进入实际任务记录。

跨文件改动使用现有任务计划；一次性教训记活跃计划，否则不为其新建制度。根据 AGENTS 与设计原则的治理等级独立复查，采用后观察与撤回，不自动反馈其他来源。源资产中的执行指令总量与入口预算共同评估，拆文件不能掩盖整体膨胀。
