---
name: init-agent-docs
description: >
  Initialize or migrate an agent-first doc system for AI collaboration.
  Creates AGENTS.md as the single entry point, docs/STRUCTURE.md, docs/ hierarchy
  with progressive disclosure, plan-as-handoff, and scripted CHANGELOG.
  Triggers when: setting up agent docs, scaffolding AGENTS.md, building AI collaboration
  guidelines, migrating README/ARCHITECTURE to agent-friendly format.
  User phrases: "帮我初始化项目的 AI 协作文档", "给仓库搭一套 Agent 文档体系",
  "把现有文档整理成 AI 能协作的格式", "set up AGENTS.md", "initialize agent-first docs".
---

# Init Agent Docs

为代码项目初始化或迁移面向 Agent 的协作文档。先交付可安全接手的最小入口，再按阶段补齐资产；不要求为执行本 Skill 全文预读参考。

`assets/...` 相对本 Skill 根；目标路径相对项目根。修改本 Skill 来源时读根 AGENTS.md；初始化目标项目时按下表路由。

## 核心约束

- AGENTS.md 是唯一行为入口，目标 ≤250 行，只放项目硬约束、必要偏好、命令绑定与导航；专题按需读。
- 可执行事实源优先：CI / hook / task runner / manifest scripts / lockfile / config > README / prose 文档 > 模板默认文案。
- 覆盖前读所有已有 instruction，保留已验证硬约束、精确命令与禁止事项；冲突和迁移去向入初始化记录。不得静默丢失用户定制。
- Git/no-Git 与规模独立；no-Git 不运行 Git、不自动 init、不生成 Git-only 资产。Git 使用实际当前分支/remote/upstream，不假定名称，不自动 stash、pull、commit 或 push。
- 已有授权持续有效，不重复确认；规模、覆盖、可选集成没有既有授权时才澄清。越权、预算或不可逆副作用须按实际边界处理。
- 模型选择任务分解、协作方式、提示词和模型；脚本处理确定性顺序、记账、路由、验收与止损。不固定组织、模型或永久拓扑。
- 派生索引交脚本，判断和内容交 Agent。机械通过不等于语义正确；执行者自检不能冒充独立验收。
- 治理正文直接写最终规范态，历史归版本记录/CHANGELOG/任务记录。新 Git 内容用 `<user-home>` 代替真实用户路径。

## Profile 摘要

| Profile | 必备交付 | 裁剪 |
|---|---|---|
| Small + Git | AGENTS、README、docs/{CURRENT,CHANGELOG,audit-checklist,initialization}.md；scripts/{changelog,audit,check_all}.py | 不建 STRUCTURE、overview、plans、memory、maintain、governance 专题；hooks 默认不装 |
| Small + no-Git | 同 Small + Git 的文件 | 另删全部 Git 命令、history/commit/hook/branch/remote/worktree 指引与资产 |
| Medium/Large + Git | Small 通用件 + STRUCTURE、overview、deployment、governance、plans、记忆与维护器 | API/pitfalls/schema 按需；Git 集成另按授权选择 |
| Medium/Large + no-Git | 同中大型文件 | 无 Git-only 内容与资产；以 CURRENT/CHANGELOG/文件状态交接 |

Small 的初始化进度唯一源是 docs/initialization.md，完成后原路径 status: done 保留；后续任务只写 CURRENT，改进候选只写审计清单。中大型进度在 docs/plans/active/initialization.md，独立验收后才移 completed/initialization.md。

## 分阶段读取

只读取当前阶段对应标题至下一个同级标题；不要为找一个段落加载整个文件。阶段粒度按任务和剩余上下文决定，无文件数阈值。

| 当前情况 | 必读材料/分区 | 产物与下一步 |
|---|---|---|
| 新初始化/迁移 | [initialization.md](assets/references/initialization.md)「调查与选项」 | 授权/profile、来源、事实出处与状态；再进入最小入口 |
| 画像足够 | 同文件「最小入口与迁移」 + AGENTS/README/CURRENT 模板 | 最小安全入口，无提前死链；再进入扩展 |
| 补充已选资产 | 同文件「扩展资产」+ 当前 profile 对应模板 + [治理合同](assets/references/governance-contract.md) | Small 提取最小合同；中大型复制专题，按生成内容更新导航 |
| 验收与交付 | 同文件「验收与交付」+ 目标审计清单 | 脚本检查、独立入口测试、出生档案完成证据 |
| 中断恢复 | 本入口 + 目标 CURRENT 指向的初始化状态 + 当前阶段分区 | 核对现场差异，续办下一步，不重读全库或全部参考 |
| 安装可选机制 | [optional-integrations.md](assets/references/optional-integrations.md) 对应节 | hooks、会话提醒或 worktree，默认不加载 |
| 复杂任务协作 | [workflow-patterns.md](assets/references/workflow-patterns.md) 对应节 | 所有权、交接、隔离与协作工具契约 |
| 设计取舍/规则维护 | [design-principles.md](assets/references/design-principles.md) 对应节；治理合同 | 适用评审等级、边界与最小候选 |
| 维护/评测本 Skill | 根 AGENTS、[eval-baseline.md](assets/references/eval-baseline.md) | L1/L1.5 分开；未跑 L2/L3 如实记录 |

拆文件不会释放已经读入的上下文；必要时写清状态后用新上下文接续。CURRENT 初始化期间只放状态入口与下一步，不抄阶段清单。

## 知识库叠加时的路径契约

普通项目用 scripts/ 和 .agents/memory/。已有 KB 叠加布局沿用 .meta/scripts/ 与 .meta/memory/：维护器重命名 docs_maintain.py，由 KB 主 maintain.py 调 --check；索引委托同目录 memory_index.py，不创建第二索引写入者。生成步骤/模板/hook 的目标路径同步替换，源 assets 路径不变。不得重建根 scripts/ 或 .agents/memory/。

通用治理服从项目既有领域规则；本 Skill 不复制 KB 检索、隐私分类、主从设备或作者分离机制，不依赖 embedding、API、常驻服务或未安装的全局 Skill。沿用既有控制器，无控制器时用项目本地合同和独立验收完成交付。

## 完成判据

选定 profile 的产物、纯文本指引、链接和命令一致；无指导注释与未填占位符（脚本管理的索引标记、下游 bugfix 写作模板除外）；检查全部通过且独立入口测试通过，才将状态置 done。未完成阶段、未运行验证和外部部署分开报告。源码通过不等于已发布或已部署。
