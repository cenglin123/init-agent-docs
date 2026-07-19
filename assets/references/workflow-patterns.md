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
   - **（推荐）使用 worktree 机制为每个 owner 创建独立工作环境**（已安装 `scripts/worktree_task.py` 时一律走四动作），避免多 Agent 共享工作树产生冲突，详见下方"工具支持：Git Worktree 与 worktree_task 四动作"
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

### 工具支持：Git Worktree 与 worktree_task 四动作

在多 Agent 并行协作时，**必须隔离不同 owner 的工作环境**——共享同一工作树意味着未提交修改互相可见、index 竞争、半成品互相污染。

**什么是 git worktree？**

Git worktree 允许你在同一个仓库的不同目录下检出不同的分支，这些工作目录共享同一个 `.git` 仓库，但各自有独立的工作区和 index。

**为什么需要隔离机制而不只是口头约定？**

多个 Agent 同时修改同一个工作树会产生冲突和混乱。推荐 worktree 是软约束——Agent 忘了切就重新暴露竞态。机制化（helper 默认路由 + canonical 分支保护 hook）把隔离变成硬约束：进入 create 后工作树和 index 物理分离；canonical 分支的历史由 hook 机械保护。

#### 机制化：worktree_task 四动作

本 skill 附带 `assets/scripts/worktree_task.py`（安装步骤见 SKILL.md 第 6.5 步）。它是四动作 Git wrapper，不保存任务状态——Git branch / worktree registration / history 是唯一事实源：

| 动作 | 行为 |
|------|------|
| `create` | 从当前 canonical 分支创建 `task/<id>` 分支与独立 linked worktree；每次调用生成新不透明 ID（同语义重复派单也得不同身份） |
| `check <id>` | 只读报告 branch / registration / clean / ahead-behind / 是否已是 canonical 祖先 |
| `integrate <id>` | 取得 per-repo 共享锁，校验 canonical 主工作树（git-dir == common-dir 且 symbolic-ref == canonical 分支）与 task 身份，复核 ref 未漂移后 `merge --ff-only` |
| `cleanup <id>` | 仅在 tip 已是 canonical 祖先、worktree clean、身份完全匹配时移除 worktree + 删分支；半缺失 fail closed |

**失败语义**（失败后 task 对象一律保留，不覆盖不清理不确定状态）：

| result | 含义 | 处置 |
|--------|------|------|
| `needs-rebase` | task 不含当前 canonical tip | 在 task worktree 内 `git rebase <canonical>` 后重试 |
| `head-drift` | 校验后 canonical/task 漂移 | 未合并未清理；复核后重试 |
| `already-integrated` | tip 已是 canonical 祖先 | 响应丢失后的安全重试结果；不重复提交 |
| `lock-busy` | canonical writer 锁被持有 | 稍后重试 |
| `partial-state` / `refused` | cleanup 身份不符 | fail closed，人工核对 |

**响应丢失恢复**：不认领原调用。重试 `create` 生成新 ID；旧对象经 `git worktree list --porcelain` 与 `git branch --list 'task/*'` 可发现，仅对可证明 clean 的对象执行 cleanup；重试 `integrate` 经 ancestry 判 `already-integrated`。

**canonical 分支快进保护 hook**（`assets/hooks/reference-transaction.sh`）：安装后，canonical 分支（默认解析 `main` → `master`，可用 `git config worktree-task.canonicalRef` 显式指定）的每次更新必须能证明快进——amend、向非后代的 reset、rebase rewrite、直接 non-FF update-ref 被机械拒绝；`task/*` 分支不受门控，owner 在 task worktree 内可自由 amend/rebase。

**git worktree 的优势：**

| 优势 | 说明 |
|------|------|
| **隔离性** | 每个 owner 有独立的工作目录和 index，互不干扰 |
| **共享 Git 历史** | 所有 worktree 共享同一个 `.git`，节省空间 |
| **独立分支** | 每个任务在不同分支上，便于代码审查和回滚 |
| **无冲突** | 不会因为同时修改同一文件而产生冲突 |
| **易于清理** | 任务完成后 cleanup 移除 worktree + 分支 |

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

手工路径只适用于 helper 未安装的项目；安装后一律走四动作（身份、校验、失败语义由 helper 保证，不靠 Agent 记忆）。

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
