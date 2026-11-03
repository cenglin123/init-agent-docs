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

**隔离边界**：worktree 仅隔离未提交文件和 index；合入冲突、跨文件语义冲突与外部系统状态仍需 Agent 协调。`worktree_task.py` 是跨 Agent 宿主共享 Git common-dir 登记的自愿协作入口，不会拦截直接写文件、手动 Git 操作、未调用它的旧工具或另一份 clone。owner 是协作声明，不是身份认证；review digest 证明快照一致，不证明语义判断正确。canonical 快进保护 hook 可单独选装，不是入场协调的必要条件。

**主工作树占用声明（main-claim）**：主工作树（canonical）只属于持有 main-claim 的 agent。primary 开工前 `claim-main --owner primary`（TTL 默认 180 分钟，同 owner 续期重置到期、过期可接管），收工 `release-main --owner primary`；`main-claim` 只读查询、`list` 显示占用；`integrate` 在存在他人活动 claim 时机械拒绝。**不要以「git status 干净」判定主工作树可用**——两次写入之间的快照必然干净，时点检查防不了撞车。fork / 子代理一律 worktree，无例外。

#### 工作树与任务入场

本 skill 附带 `assets/scripts/worktree_task.py`（安装步骤见 optional-integrations.md「多 Agent worktree」）。`create --name <显示名> --owner <标识>` 只输入一次显示名，派生稳定的 ID、`task/<id>-<slug>` 分支和 `wt-<id>-<slug>` 目录；同名新建仍是不同任务，续办用 `resume <id> --owner ... --generation ...`，不按时间抢占。`register` 可将已存在的 linked worktree 显式登记。未登记的 `task/*` 工作树和无 intent 的旧记录在 review 中是 unknown，不视为已协调。

`intent` 登记目标、非目标、自由文本范围；字面仓库相对 `--path` 只提示机械重叠，`--depends-on <peer-id>@<完整提交 SHA>` 只承认已提交代码依赖。`review` 展示所有未关闭任务及范围版本，并返回 digest。明确路径重叠、依赖、未知范围或 Agent 主动声明的语义关联需协调；相关双方在各自当前 revision 上 `coordinate` 同一份协议文本，再各自重新 `review`、`admit`。失联时可记录限定 pair、边界、理由和负责人声明的 override；CLI 无法核验该声明的真实授权。自己的范围或相关 peer 范围/结论变化会使 admission 失效，无关 peer 变化只提示刷新。范围由 Agent 判断，不用 path 命中机械否决并行。

`check <id> --write --owner ... --generation ...` 是动笔前主动调用的软门禁；普通 `check`、`list`、`review`、`resume` 不写登记或创建锁。所有状态变更和整合共用 Git common-dir 原子锁，锁无超时自动接管；残留锁须核对任务和 Git 状态后由项目负责人按本地流程人工恢复，不能仅凭时间或 PID 删除。登记保留在 common-dir，不进入提交。Git worktree registration、branch、commit 仍是文件与历史事实源；登记只承载协作状态。

原有四动作及其调用方式继续可用：

| 动作 | 行为 |
|------|------|
| `create` | 无 `--name/--owner` 时创建旧式 opaque ID 工作树，需显式登记/处置才可视为已协调 |
| `check <id>` | 只读报告 branch / registration / clean / ahead-behind / 是否已是 canonical 祖先；`--write` 另检查入场状态 |
| `integrate <id>` | 取得 Git common-dir 共享锁，校验 canonical 与 task 身份、复核 ref 未漂移后 `merge --ff-only` |
| `cleanup <id>` | 拒绝未合入、不干净、含未跟踪或 ignored 数据的工作树；旧式任务成功后删除分支，已登记任务须先 clean+integrated `close`，清理后保留分支与登记作审计 |

**失败语义**（失败后 task 对象一律保留，不覆盖不清理不确定状态）：

| result | 含义 | 处置 |
|--------|------|------|
| `needs-rebase` | task 不含当前 canonical tip | 在 task worktree 内 `git rebase <canonical>` 后重试 |
| `head-drift` | 校验后 canonical/task 漂移 | 未合并未清理；复核后重试 |
| `already-integrated` | tip 已是 canonical 祖先 | 响应丢失后的安全重试结果；不重复提交 |
| `lock-busy` | common-dir 锁被持有 | 核实持有者与状态，不按超时夺锁 |
| `partial-state` / `refused` | cleanup 身份不符 | fail closed，人工核对 |

**响应丢失恢复**：新建已返回 ID 时用 `resume` 验证 owner/generation；不知道 ID 时先 `list` 和 `git worktree list --porcelain`，不重试创建冒充恢复。`creating` 半状态不能 `resume`，也没有自动修复命令：停止写入，记录 ID/路径，核对 common-dir 登记、分支、Git worktree registration、实际文件和提交；由项目负责人确认归属与无唯一数据后，按项目恢复流程显式修复或回滚，不能凭时间删除登记或夺锁。重试 `integrate` 经 ancestry 判 `already-integrated`。

**canonical 分支快进保护 hook**（`assets/hooks/reference-transaction.sh`）：安装后，canonical 分支（默认解析 `main` → `master`，可用 `git config worktree-task.canonicalRef` 显式指定）的每次更新必须能证明快进——amend、向非后代的 reset、rebase rewrite、直接 non-FF update-ref 被机械拒绝；`task/*` 分支不受门控，owner 在 task worktree 内可自由 amend/rebase。

**git worktree 的优势：**

| 优势 | 说明 |
|------|------|
| **隔离性** | 每个 owner 有独立的未提交文件和 index |
| **共享 Git 历史** | 所有 worktree 共享同一个 `.git`，节省空间 |
| **独立分支** | 每个任务在不同分支上，便于代码审查和回滚 |
| **协调范围** | 入场快照和同文协议记录重叠与依赖；仍需 Agent 判断语义 |
| **可审计清理** | 任务完成后清理 worktree；已登记任务保留分支与记录 |

**注意事项：**

- worktree 根目录默认在仓库父目录的 `<仓库名>.worktrees/`（可用 `git config worktree-task.worktreeRoot` 覆盖），避免混入项目本身的文件结构
- 协调人用 `git worktree list` 或 `worktree_task.py check <id>` 定期检查活跃 task，避免遗留孤儿；孤儿只清理可证明 clean 的对象
- 工作树内脚本若按"脚本位置向上找仓库根"定位，会自动指向 worktree 自身——派生数据类脚本（embedding 重建、全量 lint 等）应只在主工作树运行，集成后统一执行

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
