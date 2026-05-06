# init-agent-docs — skill maintainer notes

此 README 面向**维护本 skill 的人或 agent**（不是执行 skill 的 agent）。执行指令请看 [SKILL.md](SKILL.md)。

## 这个 skill 做什么

为一个代码仓库初始化"面向 AI agent 协作"的文档体系：

- `AGENTS.md`（同步到 `CLAUDE.md` / `GEMINI.md`）：行为规则 + 信息导航
- `STRUCTURE.md`：架构文档总索引
- `CHANGELOG.md`：倒序变更记录
- `scripts/changelog.py`：CHANGELOG 标题树、局部读取和追加
- `scripts/agent_links.py`：`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 同步检查与修复
- `docs/{overview,api,deployment,pitfalls,CURRENT}.md`：专题文档（中型 / 大型项目；小型项目只保留 `CURRENT.md`）
- `docs/plans/{active,completed}/`：执行计划目录（中型及以上才创建；小型项目用 `docs/initialization.md` 作为出生档案）
- `.githooks/`：可选 lint 质量门控，调用 `scripts/agent_links.py` 做同步兜底

背后的设计哲学见 SKILL.md"设计哲学"一节。

## 目录结构

```
init-agent-docs/
├── SKILL.md                              # 主指令（执行 skill 的 agent 读这个）
├── README.md                             # 你现在读的这份文件
└── assets/
    ├── templates/
    │   └── zh/                           # 中文模板集（9 个 .tpl）
    ├── scripts/
    │   ├── changelog.py                  # CHANGELOG 脚本化维护
    │   └── agent_links.py                # 同步检查与修复
    ├── hooks/
    │   ├── pre-commit-python.sh          # ruff / flake8
    │   ├── pre-commit-node.sh            # eslint / prettier
    │   ├── pre-commit-go.sh              # gofmt / go vet
    │   ├── pre-commit-generic.sh         # 空壳，自己填
    │   └── pre-commit-config.yaml        # 给使用 pre-commit 框架的项目
    └── pitch/
        └── presentation.html             # 对外分享用的 pitch deck，不是运行时产物
```

## 模板占位符约定

模板里使用两种占位形式：

- `[方括号]`：给执行 agent 看的"此处替换为具体值"（如 `[项目名]`、`[今天的日期]`）
- `<!-- HTML 注释 -->`：给执行 agent 看的填写指导，生成最终文件时应替换为实际内容或整段删除

**不用 `{{mustache}}` 风格的原因**：这些占位符需要 agent 根据项目上下文灵活填写，不是机械字符串替换；用人类可读的方式描述"这里应该写什么"比变量名更有用。

## 已知限制

1. **同步与文件系统**：`agent_links.py` 提供 copy 和 hardlink 两种同步模式。默认 `repair` 使用 copy 模式（最可靠，不受编辑器原子写入影响）；如文件系统支持且你明确需要 hardlink，可显式传 `--mode=hardlink`。在 AGENTS.md 顶部写清当前项目用哪种模式，避免歧义。
2. **编辑器原子写入**：部分编辑器（VS Code 某些模式、部分 IDE）用"写临时文件 → 删原文件 → 重命名"保存。hardlink 模式下这会断开链接；copy 模式不受影响。如使用 hardlink，依赖 pre-commit hook 检测并重新运行 repair 来兜底。
3. **模板仅一种语言**：当前只附带 zh/。其他语言需要手工复制 zh 目录并翻译；`scripts/changelog.py` 内置了对英文 CHANGELOG 标题的识别，所以即使模板只有中文，用户后续手写英文条目仍能正确归类。
4. **pre-commit 片段没跑过所有平台**：Windows 原生 Git Bash 下 `xargs` 对空输入的处理偶有差异；如遇问题，用 `if [ -n "$STAGED" ]; then echo "$STAGED" | ...; fi` 兜住。

## 维护指引

- 修改模板后，手工在一个测试项目上跑一遍 skill 看是否还通顺。
- 如果新增一个模板文件，记得在 zh/ 下添加，并在 SKILL.md 的"目标文件结构"一节补说明。
- 维护 CHANGELOG 相关规则时，优先改 `assets/scripts/changelog.py` 的能力和 AGENTS 模板中的调用说明，不要把手工插入流程重新塞回模板。
- 维护同步规则时，优先改 `assets/scripts/agent_links.py` 和 hook 调用，不要要求 Agent 记平台差异命令。
- 维护方法论时，只保留跨项目可迁移、能解决真实问题的原则（如 Occam / Bitter Lesson），不要复制不必要的治理形式或组织隐喻。
- 哲学条款尽量保留，增改需要在 SKILL.md 顶部说清"为什么"——本 skill 的价值一半以上在于设计哲学的阐释，纯模板替换价值有限。
- `assets/pitch/presentation.html` 是宣讲 deck，和执行流程无关，但核心方法论变化时应同步更新。
