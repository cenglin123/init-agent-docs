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
