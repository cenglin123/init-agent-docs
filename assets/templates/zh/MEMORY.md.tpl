# 项目记忆索引

> Agent 启动或 compact 恢复时应读取本文件。
> 关键摘要已内联在 AGENTS.md「项目记忆」段——本文件是详细版本。
> **索引段由 `python scripts/maintain.py` 自动重建——agent 只负责记忆的沉淀与检索，禁止手工编辑标记段内容。**

<!-- ⓘ 本文档的治理规则见 AGENTS.md「文档维护原则 → docs/ 文件的治理规则」段 -->

## 记忆条目索引

<!-- memory-index:start -->
（本段由 scripts/maintain.py 自动重建。初始化后运行一次 `python scripts/maintain.py --memory-index` 生成首版索引。）
<!-- memory-index:end -->

## 记忆规则

### 写入条件

- `user/role.md`：首次透露偏好 / 用户明确要求 / ≥2 次同模式反馈
- `project/`：用户说"我要做 X 项目" / 多轮对话深入且跨会话
- `feedback/`：用户明确评价输出 / 同一类修正 ≥2 次

### 写入前查重

新建记忆文件前，先读上方索引确认是否已有相似条目：
- 高相似 → 更新现有文件
- 中等相似（同主题不同视角）→ 新文件引用旧文件
- 低相似 → 正常新增

### 维护分工

- **Agent 负责**：记忆的沉淀（写入 / 更新记忆文件）与检索（任务前读索引）；更新记忆后同步 AGENTS.md「项目记忆」内联摘要
- **脚本负责**：MEMORY.md 索引段由 `python scripts/maintain.py` 每次维护自动重建；`.agent/memory/` 持续 30 天无更新 → 维护报告提示"记忆目录空转"
