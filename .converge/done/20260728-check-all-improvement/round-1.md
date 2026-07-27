# Converge R1 — Reviewer 审计报告

> 审查对象：init-agent-docs 改进计划（基于 novel_world_one 治理重构经验）
> 日期：2026-07-28

```yaml
verdict: 需修复
hard_blocks:
  - id: H1
    description: >
      frontmatter-schemas.md.tpl 在 SKILL.md 执行步骤中没有对应生成指令。
      AGENTS.md.tpl 指向 docs/frontmatter-schemas.md，但 SKILL.md 第 2 步
      未包含将此模板写入目标项目的步骤 → 生成项目中出现死链。
    fix_direction: >
      在 SKILL.md 第 2 步中型项目表格追加 `docs/frontmatter-schemas.md` →
      `frontmatter-schemas.md.tpl`；STRUCTURE.md.tpl 索引表追加对应行。
    fixed: true

  - id: H2
    description: >
      check_all.py 无法替代完工清单全部 7 条散文项。"验证""复查视角""跳过条件"
      三项需主观判断，脚本自动检查会静默丢弃。
    fix_direction: >
      两层设计：(a) check_all.py 机械层 (b) 手工确认层（3 条）。
      AGENTS.md.tpl 写"先跑 check_all.py，再逐项确认"。
    fixed: true

  - id: H3
    description: >
      行数上限 200→250 需跨 9 处同步，任一遗漏造成系统内矛盾。
      受影响：SKILL.md(×4) audit.py(×3) AGENTS.md.tpl audit-checklist.md.tpl eval-baseline.md
    fix_direction: 全仓 grep → 逐处更新。
    fixed: true

soft_blocks:
  - id: S1
    description: >
      check_all.py 与 audit.py 职责重叠。audit.py 已聚合 7 项检查，
      check_all.py 再做会产生"何时用哪个"混淆。
    severity: 高
    fix_direction: >
      check_all = 高频完工（静默 ~5 项），audit = 深度定期（详实 ~15 项）。
      在两个脚本 docstring 和 SKILL.md 第 9 步明确分工。
    fixed: true

  - id: S2
    description: >
      项目记忆段压缩后，需确认 MEMORY.md.tpl 能独立指导 Agent 完成所有记忆操作。
    severity: 中
    fix_direction: 触发条件保留在 AGENTS.md；实现细节留 MEMORY.md/tpl。
    fixed: true

  - id: S3
    description: >
      记忆检索/Bugfix 触发条件必须留在 AGENTS.md 不能下沉。当前模板已保留
      触发条件但标签"触发词硬性前置"被改写，需确认测试能匹配新措辞。
    severity: 高
    fix_direction: 保留触发条件文字，测试改用"检索动作必须发生"匹配。
    fixed: true

  - id: S4
    description: 行数上限 250 需在哲学节给出理由。
    severity: 中
    fix_direction: 补充"200 理想 vs 250 可执行上限"的说明。
    fixed: true

flags:
  - id: F1
    description: 反模式 #3/#14 与 check_all.py 的关系需审视
    disposition: 追加反模式 #23（清单散文枚举）和 #24（AGENTS 百科全书）
  - id: F2
    description: 行数阈值改后旧项目标准不变——模板更新不回溯
    disposition: 已知限制，不改
  - id: F3
    description: 文档维护原则 14→5 取舍标准需说清
    disposition: 已在计划中记录保留判据
  - id: F4
    description: SKILL.md 第 1 步 cp 命令缺 check_all.py
    disposition: 已修复
```
