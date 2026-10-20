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

**角色分工（领域交接角色，归属于当前选定的控制器）：**

| 角色 | 职责 | 不拥有的权限 |
|------|------|------------|
| **Coordinator** | 拆解任务、分配 owner/reviewer、维护任务分配表、汇总结果 | 不拥有全局流程模式、预算、终端决策或自动修复循环 |
| **Owner** | 领取任务、执行实现、提交代码、更新计划状态 | 不拥有自审批或全局编排权限 |
| **Reviewer** | 在新上下文中复查代码、验证通过后将任务标记为完成 | 不拥有预算、模式切换或终端裁决权限 |

以上角色是**领域交接角色**，不是顶层控制器。它们不拥有全局模式、不签发终局结论、不自行启动反复修复循环。全局流程模式、预算门、角色转换和终端决策由当前选定的控制器（如 Converge）负责。如果未选定控制器，由用户直接协调。

**工作流程：**

1. **任务拆解**：
   - 协调人分析任务，拆分为多个可并行的子任务或阶段
   - 为每个子任务分配 owner 和 reviewer
   - 将任务分配表写入计划文件

2. **并行执行**：
   - 不同 owner 在各自的窗口中领取任务（状态从 `queue` 改为 `in_progress`）
   - **（推荐）使用 worktree 机制为每个 owner 创建独立工作环境**（已安装 `scripts/worktree_task.py` 时走其领取与入场流程），隔离共享工作树中的未提交文件和 index；合入和语义冲突仍须协调，详见下方「工具支持」
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

### 工具支持：Git Worktree 与 worktree_task 协作入口

在多 Agent 并行协作时，**必须隔离不同 owner 的工作环境**——共享同一工作树意味着未提交修改互相可见、index 竞争、半成品互相污染。

**什么是 git worktree？**

Git worktree 允许你在同一个仓库的不同目录下检出不同的分支，这些工作目录共享同一个 `.git` 仓库，但各自有独立的工作区和 index。

**隔离边界**：worktree 仅隔离未提交文件和 index；合入冲突、跨文件语义冲突与外部系统状态仍需 Agent 协调。`worktree_task.py` 是跨 Agent 宿主共享 Git common-dir 登记的自愿协作入口，不会拦截直接写文件、手动 Git 操作、未调用它的旧工具或另一份 clone。owner 是协作声明，不是身份认证；review digest 证明快照一致，不证明语义判断正确。canonical 快进保护 hook 可单独选装，不是入场协调的必要条件。

**主工作树占用声明（main-claim，2026-10-20 起）**：主工作树（canonical）只属于持有 main-claim 的 agent。primary 开工前 `claim-main --owner primary`（TTL 默认 180 分钟，同 owner 续期重置到期、过期可接管），收工 `release-main --owner primary`；`main-claim` 只读查询、`list` 显示占用；`integrate` 在存在他人活动 claim 时机械拒绝。**不要以「git status 干净」判定主工作树可用**——两次写入之间的快照必然干净，时点检查防不了撞车（2026-10-20 双守规 agent 实测碰撞）。fork / 子代理一律 worktree，无例外。

#### 工作树与任务入场

本 skill 附带 `assets/scripts/worktree_task.py`（安装步骤见 SKILL.md 第 6.5 步）。`create --name <显示名> --owner <标识>` 只输入一次显示名，派生稳定的 ID、`task/<id>-<slug>` 分支和 `wt-<id>-<slug>` 目录；同名新建仍是不同任务，续办用 `resume <id> --owner ... --generation ...`，不按时间抢占。`register` 可将已存在的 linked worktree 显式登记。未登记的 `task/*` 工作树和无 intent 的旧记录在 review 中是 unknown，不视为已协调。

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

### 两种模式的对比

| 维度 | 单 Agent 跨上下文 | 多 Agent 并行协作 |
|------|-----------------|-------------------|
| **适用场景** | 中等复杂度、顺序执行 | 高复杂度/高风险、可并行 |
| **计划复杂度** | 阶段划分即可 | 需要任务分配表 + 状态流转 |
| **Owner 数量** | 1 个（顺序推进） | 多个（并行推进，可用 git worktree 隔离） |
| **验证方式** | 自检或可选 reviewer | 每个 task 必须有 reviewer |
| **CURRENT.md** | 可作为轻量交接协议 | 只保留全局摘要，不作为唯一真相源 |
| **风险** | 上下文用完需中断 | 需要协调人避免冲突 |

### 计划文件结构

计划模板在 `assets/templates/zh/plan.md.tpl`。关键字段：

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
