---
title: 执行计划与跨上下文工作流参考
purpose: 供 init-agent-docs skill 在执行初始化时按需引用，不常驻上下文
description: >
  详细说明单 Agent 跨上下文和多 Agent 并行两种工作模式、git worktree 用法、
  阶段粒度控制、协调人职责，以及计划文件的生命周期管理。
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

### 工作方式与交接

Agent 根据目标、风险、依赖和上下文选择直接执行、分阶段或并行；不固定模型、组织或拓扑。计划记录谁执行、谁独立验收、写集/依赖、当前状态和下一步。Coordinator / Owner / Reviewer 是可选职责称呼，不是永久角色或顶层控制器。

已选控制器继续掌握流程模式、预算与终端决策，不另建平行控制器；未选控制器时用项目本地合同与独立检查完成交付，不强制安装外部 Skill。已有授权直接适用，不逐阶段重复申请。

阶段结束更新计划为 review 或已验收，保存实际变更、核实事实出处、未决项、下一步和须读材料。阶段以可验证、可交接为界，按任务与剩余上下文选择粒度，无文件数或行数硬阈值。Git 提交按授权处理，不把 commit 当所有交接的先决条件。

并行任务必须明确所有权并隔离写集；强耦合修改顺序执行。执行者可在授权范围内选分工/委派，但须更新责任与交接，语义冲突及外部副作用仍需协调。CURRENT 只保留计划入口，不重复任务表。独立验收与执行分离；风险等级沿用项目合同。

### 工具支持：Git Worktree 与 worktree_task 协作入口

在多 Agent 并行协作时，**必须隔离不同 owner 的工作环境**——共享同一工作树意味着未提交修改互相可见、index 竞争、半成品互相污染。

**什么是 git worktree？**

Git worktree 允许你在同一个仓库的不同目录下检出不同的分支，这些工作目录共享同一个 `.git` 仓库，但各自有独立的工作区和 index。

**隔离边界**：worktree 仅隔离未提交文件和 index；合入冲突、跨文件语义冲突与外部系统状态仍由主控 Agent / 人类协调。`worktree_task.py` 是轻量本地 Git 隔离与占用声明工具，不会拦截直接写文件、手动 Git 操作或另一份 clone。canonical 快进保护 hook 可单独选装，不是隔离的必要条件。

**主工作树占用声明（main-claim）**：主工作树（canonical）只属于持有 main-claim 的 agent。primary 开工前 `claim-main --owner primary`（TTL 默认 180 分钟，同 owner 续期重置到期、过期可接管，他人活动 claim 不允许 `--force` 强夺），收工或整合前 `release-main --owner primary`；`main-claim` 只读查询、`list` 显示当前活跃 worktrees 与占用状态；`integrate` 在存在任何活动 claim 时机械拒绝（整合前须先释放）。**不要以「git status 干净」判定主工作树可用**——两次写入之间的快照必然干净，时点检查防不了撞车。fork / 子代理一律开 worktree。

#### 工作树四动作与外包施工节奏

本 skill 附带 `assets/scripts/worktree_task.py`（安装步骤见 optional-integrations.md「多 Agent worktree」）。所有写状态变更（含 `claim-main` / `release-main`）和整合共用 Git common-dir 原子锁，锁无超时自动接管；残留锁须核对任务和 Git 状态后由项目负责人人工恢复，不能仅凭时间或 PID 删除。Git worktree registration、branch、commit 是唯一文件与历史事实源。

| 动作 | 行为 |
|------|------|
| `create [--name <显示名> --owner <标识>] [--base <commit-sha>]` | 在 common-dir 锁内创建独立分支（`task/<id>` 或 `task/<id>-<slug>`）与独立工作目录（`<仓库名>.worktrees/wt-...`）；`--name` 与 `--owner` 需成对传入或同时省略，`--base` 仅接受完整 commit SHA |
| `check <id>` | 只读报告 branch / registration / clean / ahead-behind / 是否已是 canonical 祖先及当前 `main-claim` 状态 |
| `integrate <id>` | 取得 common-dir 原子锁，锁内复核无活动 `main-claim`、校验 canonical 与 task 身份及路径边界、复核 ref 未漂移后按精确提交 SHA 执行 `merge --ff-only` |
| `cleanup <id>` | 取得 common-dir 原子锁，校验路径边界并拒绝未合入、不干净、含未跟踪或 ignored 用户数据及孤立残留目录（fail-closed）；通过后移除 worktree 并删除对应 `task/*` 分支 |
| `list` | 只读列出当前活跃的 linked `task/*` worktrees 与 `main-claim` 状态 |
| `claim-main` / `release-main` / `main-claim` | 主工作树占用声明、释放与只读查询 |

**外包施工验收节奏（委派子代理 / OCSR / Codex executor 时）**：
- 施工方在 `create` 分配的独立 worktree 内修改代码，**优先不自动 `git commit`**，将改动留在工作区；
- 主控方或独立 reviewer 同时检查 `git status`（覆盖未跟踪新文件）与 `git diff` 并运行测试；打回返工时零半成品 commit 污染历史；
- 验收通过后再由主控方在 task worktree 内 `git add <具体路径> && git commit`，若当前持有主树占用先执行 `release-main`，再依次执行 `integrate <id>` 与 `cleanup <id>`；
- 若需在 worktree 内放置临时任务单或交接文件，通过 `git rev-parse --git-common-dir` 定位共享 Git 目录写入 `info/exclude`（兼容 `.git` 为 gitfile 的工作树），不污染 `.gitignore`；**注意 `cleanup` 会检查 `--ignored` 数据，清理前须将临时交接文件移出或删除**。

**失败语义**（失败后 task 对象一律保留，不覆盖不清理不确定状态）：

| result | 含义 | 处置 |
|--------|------|------|
| `needs-rebase` | task 不含当前 canonical tip | 在 task worktree 内 `git rebase <canonical>` 后重试 |
| `head-drift` | 校验后 canonical/task 漂移 | 未合并未清理；复核后重试 |
| `already-integrated` | tip 已是 canonical 祖先 | 响应丢失后的安全重试结果；不重复提交 |
| `lock-busy` | common-dir 锁被持有 | 核实持有者与状态，不按超时夺锁 |
| `partial-state` / `refused` | 身份不符、存在他人活动 `main-claim` 或含未清理数据 | fail closed，人工核对 |

**响应丢失恢复**：先运行 `list` 与 `git worktree list --porcelain` 核对实际已创建的分支与工作目录，不盲目重试创建冒充恢复；重试 `integrate` 经 ancestry 判定返回 `already-integrated`。

**canonical 分支快进保护 hook**（`assets/hooks/reference-transaction.sh`）：安装后，canonical 分支（默认解析 `main` → `master`，可用 `git config worktree-task.canonicalRef` 显式指定）的每次更新必须能证明快进——amend、向非后代的 reset、rebase rewrite、直接 non-FF update-ref 被机械拒绝；`task/*` 分支不受门控，owner 在 task worktree 内可自由 amend/rebase。

**注意事项**：
- worktree 根目录默认在仓库父目录的 `<仓库名>.worktrees/`（可用 `git config worktree-task.worktreeRoot` 或 `--wt-root` 覆盖），避免混入项目本身的文件结构；
- 定期用 `list` 或 `git worktree list` 排查孤儿 worktree，只清理可证明 clean 且已合入的对象；
- 工作树内脚本若按「脚本位置向上找仓库根」定位，会自动指向 worktree 自身——派生数据类脚本（embedding 重建、全量 lint 等）应在主工作树集成后统一执行。

**不使用隔离机制的风险：**

多个 Agent 在同一个工作树上工作会导致：
- 未提交的修改互相可见、互相覆盖
- git index 竞争（`git add` / commit 交错）
- 半成品代码污染其他 owner 的工作区
- 难以追溯谁改了什么，代码审查困难

#### 手工命令（helper 不可用时的降级路径）

```bash
# 为 owner A / B 各建独立分支和 worktree
git worktree add ../project-owner-a feature/owner-a-task
git worktree add ../project-owner-b feature/owner-b-task

# 查看 / 清理
git worktree list
git worktree remove ../project-owner-a
```

手工路径只适用于 helper 未安装的项目；安装后由 Agent 主动使用 helper 的领取、入场与整合入口。CLI 校验自己的登记和 Git 状态，但不是身份认证或全局文件写入拦截器。

---

### 计划记录与完成

使用 assets/templates/zh/plan.md.tpl，按实际需要保留任务分配、阶段与依赖、验证标准、执行/验收者、决策、风险和交接。阶段状态可 queue / claimed / in_progress / review / blocked / completed；文件 frontmatter 的 status 只写 in_progress / done / cancelled，二者不要混淆。

新上下文先读入口与 CURRENT 指向的计划，核对现场差异，再只读当前阶段材料。阶段末完成适用验证，独立验收后才关闭；计划完成移 completed，CHANGELOG 用脚本记录原因与证据，相关设计归现有专题。Small 用 CURRENT 交接普通任务，初始化出生档案不作日常状态，规则候选使用审计清单。
