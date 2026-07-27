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

<!-- 不需要 frontmatter schema 的项目跳过本文件，并删除 AGENTS.md 信息导航中对应行 -->
