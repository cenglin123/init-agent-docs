# 当前任务状态

> 只记录"此刻在做什么、做到哪了、下一步是什么"，不做历史累积。
> 初始化期间只放初始化状态文件的入口与下一步，不重复阶段清单；验收后再用于普通任务。
<!-- Small profile only -->
> Small 初始化状态在 docs/initialization.md；出生档案完成后原路径保留且不被普通任务覆盖。
<!-- /Small profile only -->
<!-- Medium/Large profile only -->
> 中大型初始化与复杂任务的状态只在关联计划中维护，本文件只留入口；并行时不抄 owner 状态表。
<!-- /Medium/Large profile only -->

<!-- 文件治理：Small 见 AGENTS.md「文件治理」；Medium/Large 见 STRUCTURE.md「文件治理」。只保留实际 profile 的指引，生成后删除本注释。 -->

## 当前任务

<!-- 1-3 行说明当前正在做什么 -->

## 当前模式

<!-- 直接执行 | 分阶段 | 协作 -->

## 当前负责人

<!-- 单 Agent 可写当前执行者；多人协作可写 coordinator / leader -->

## 下一步

<!-- 下一步最具体、可执行的动作 -->

<!-- Small profile only -->
<!-- 小型项目：初始化期间只指 docs/initialization.md；后续普通任务 handoff 直接内联本文件。 -->

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
