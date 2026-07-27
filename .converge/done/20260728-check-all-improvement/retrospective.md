# 收敛回溯

> 触发：基于 novel_world_one 治理重构的实践经验，改进 init-agent-docs
> 日期：2026-07-28
> 轮数：1 轮（verdict: 需修复 → 全部修复后收敛）

## 改动总结

1. **新增 `check_all.py`**：高频完工检查器，`--quiet` 无输出=通过，FAIL 自带修复指引
2. **新增 `frontmatter-schemas.md.tpl`**：frontmatter 字段独立权威文档
3. **AGENTS.md.tpl 压缩**：235→123 行。完工清单 1 条命令替代 7 条散文；硬约束不枚举 hooks；文档维护原则 14→5；记忆/Bugfix/Worktree 下沉
4. **行数上限 200→250**：跨 9 处同步
5. **多文档同步**：SKILL.md、README.md、STRUCTURE.tpl、audit.py、audit-checklist.tpl、eval-baseline.md、测试

## 最终状态

- 11 文件改动，净增 107 行
- 64/64 测试通过
- AGENTS.md.tpl：123 行（在 250 行上限内）

## 收敛判定

1 轮收敛。零残留硬阻断。软阻断全修复。
