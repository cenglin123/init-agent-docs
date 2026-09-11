# 当前任务状态

> 只记录"此刻在做什么、做到哪了、下一步是什么"，不做历史累积。
> 任务完成后清空或覆盖。复杂任务请指向 `docs/plans/active/` 中的详细计划。
>
> **多 Agent 并行时**：本文件不是真相源。把任务分配表、状态流转、owner/reviewer 全部写进
> `docs/plans/active/<计划名>.md`；本文件只保留"当前活跃计划入口指针"。否则多个 owner
> 会互相覆盖，状态彻底失真。

<!-- ⓘ 本文档的治理规则见 AGENTS.md「文档维护原则 → docs/ 文件的治理规则」段 -->

## 当前任务

<!-- 1-3 行说明当前正在做什么 -->

## 当前模式

<!-- 直接执行 | 分阶段 | 协作 -->

## 当前负责人

<!-- 单 Agent 可写当前执行者；多人协作可写 coordinator / leader -->

## 下一步

<!-- 下一步最具体、可执行的动作 -->

<!-- Small profile only -->
<!-- 小型项目：任务简单，不建 plans 目录，handoff 信息直接内联在此文件中。 -->

## 交接记录

<!-- 任务中断或交接时，简要记录当前状态、已完成内容、待办事项。
     新会话或新 Agent 读取本文件即可恢复上下文。
     Git profile: 也可参考 git log 查看最近提交。
     no-Git profile: 本文件是主要的 handoff 载体。 -->

<!-- /Small profile only -->

<!-- Medium/Large profile only -->
## 关联计划

<!-- 复杂任务：填写 docs/plans/active/xxx.md；没有可写 无 -->
<!-- /Medium/Large profile only -->
