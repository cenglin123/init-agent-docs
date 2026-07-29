# Frontmatter Schema

> 各文件类型的 frontmatter 字段定义。唯一权威源——AGENTS.md 与相关子文档的 schema 引用均指向此处。

<!-- 按项目实际使用的文件类型逐项填写。每个 schema 包含：
     - 文件路径模式（如 `02_人物/<角色名>.md`）
     - 完整 YAML 代码块（含注释说明各字段含义）
     - 白名单判据（如有）-->

## 示例：人物卡（`characters/<角色名>.md`）

```yaml
---
status: alive        # alive|dead|departed|unknown
role: protagonist    # protagonist|antagonist|deuteragonist|supporting|minor
# 按项目需要增删字段
---
```

## 计划（`docs/plans/active|completed/<计划名>.md`）

```yaml
---
status: in_progress       # in_progress | done | cancelled
mode: direct-execution    # direct-execution | phased | collaborative
coordinator: ""           # 协调人；单 Agent 场景留空
created_at: ""            # YYYY-MM-DD
---
```

说明：
- `status` 字段被 `scripts/audit.py plans` 检查使用：`status=done` 或 `status=cancelled` 时审计脚本会报告 STALE（应归档到 `completed/`）。
- `liveness` 字段不在此处使用——计划文件完成后即归档，不需要活性追踪。

<!-- 不需要 frontmatter schema 的项目跳过本文件，并删除 AGENTS.md 信息导航中对应行 -->
