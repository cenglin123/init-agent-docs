# 可选集成

只在已选择对应能力时读该节。no-Git 跳过全部 Git 集成。

## 质量 hooks（默认跳过）


**按需执行**：质量门控的价值在 lint / format 强制、记忆结构兜底和治理文档修改提醒；项目没有任何 lint 需求且未启用记忆系统时，可以整步跳过（Occam——不要为安装而安装）。

1. 确认脚本已经复制到项目：

   ```bash
   python scripts/changelog.py titles --limit 3
   ```

2. **按 repository mode 分支**：no-Git profile 跳过整个 hook 步骤，不创建 `.git`、`.githooks` 或 pre-commit 配置。只有用户明确确认将 no-Git 目标转换为 Git 后才可运行 `git init`，随后重新确认 profile；不得把初始化 Git 当成质量门控的默认动作。

3. **仅 Git profile 且用户已单独确认时配置 pre-commit hook**——hook 承担三类机械检查：项目栈的 lint / format（技术栈 hook 内置）、记忆目录结构兜底（`.agents/memory/` 存在时 MEMORY.md 必须存在且非空）、治理文档修改提醒（WARN，提示走独立视角复查，不阻塞提交）。未确认安装 hook 时跳过本项。

   **二选一，不要叠加**——两条路径都设置 hook 入口，叠加会跑两次、输出混乱。

   **路径 A：项目需要 lint / format 检查 → 直接复制对应技术栈 hook**

   - Python 项目 → `assets/hooks/pre-commit-python.sh`
   - Node/TS 项目 → `assets/hooks/pre-commit-node.sh`
   - Go 项目 → `assets/hooks/pre-commit-go.sh`
   - 混合 / 特殊栈 → `assets/hooks/pre-commit-generic.sh`（自行补 lint 命令）

   ```bash
   mkdir -p .githooks
   cp assets/hooks/pre-commit-python.sh .githooks/pre-commit   # 按栈替换文件名
   chmod +x .githooks/pre-commit
   git config core.hooksPath .githooks
   ```

   PowerShell 等价：

   ```powershell
   New-Item -ItemType Directory -Force .githooks
   Copy-Item assets\hooks\pre-commit-python.sh .githooks\pre-commit
   git config core.hooksPath .githooks
   ```

   **Windows 注意**：hook 是 bash 脚本，需要 git bash 解释（绝大多数 Windows 安装 Git for Windows 时已自带）。如果项目要求纯 PowerShell 路径，改用路径 B 的 `pre-commit` 框架方案（跨平台）。

   **路径 B：使用 `pre-commit` 框架（推荐给跨平台 / 多语言混合项目）**

   `pre-commit` 是一个跨平台的 hook 管理工具，能在 Windows / Linux / macOS 上一致地执行 Python 写的 hook，且自动处理 git hook 安装、版本固定、虚拟环境隔离。安装即用：

   ```bash
   pip install pre-commit
   cp assets/hooks/pre-commit-config.yaml .pre-commit-config.yaml
   pre-commit install
   ```

   PowerShell 等价：

   ```powershell
   pip install pre-commit
   Copy-Item assets\hooks\pre-commit-config.yaml .pre-commit-config.yaml
   pre-commit install
   ```

   `assets/hooks/pre-commit-config.yaml` 内置通用检查（trailing-whitespace 等），语言 lint 段落以注释形式给出，按项目实际栈解开注释即可；记忆结构兜底与治理提醒在框架路径下需按需自行补写 local hook。这条路径与路径 A 互斥——选了它就不要再用 `git config core.hooksPath .githooks`，`pre-commit install` 会接管 `.git/hooks/pre-commit`。


## 会话级治理提醒（默认跳过）

pre-commit 只在提交时触发；「编辑后不提交就走人」会完全绕过钩子。本步用宿主扩展点补一条**会话级半硬约束**，让治理目录的脏区在每个会话边界强制可见：

1. 复制 `assets/plugins/governance-watch.js` 到宿主插件目录（opencode：`~/.config/opencode/plugins/`，自动加载）
2. 修改文件头部常量：`GOV_REPO`（受治理的 git 仓库根）、`GOV_PATHS`（仓库内受治理路径）、`ENTRY_FILE`（宿主保证常驻上下文的入口文件，opencode 下即全局 `~/AGENTS.md`）。**`ENTRY_FILE` 必须位于 `GOV_REPO` 监视路径之外**——否则插件自写的提醒行会使入口文件永久处于脏区，假阳性循环
3. 实测双向：制造脏区 → 入口文件出现提醒行；恢复干净 → 提醒行消失
4. Claude Code 宿主等价实现：settings.json 的 SessionStart hook 回显同样提醒（stdout 注入上下文）；无扩展点的宿主如实保持软约束，不伪造覆盖

提醒检测与处置边界见 design-principles.md。知识库技能的 kb-guard.js 是动作侧门禁（pre-tool deny + compact 哨兵），与本插件互补、可并存；仅当宿主里已有其他**脏区提醒类**会话级插件时复用之，不同质不叠加。

## 多 Agent worktree（默认跳过）

**触发条件**：调查阶段 确认项目经常多 Agent / 多窗口并行（协作模式倾向），且用户同意安装。单 Agent 顺序推进的项目**跳过本步**——机制成本不为偶发场景预付（Occam）；将来协作成为常态时可随时补装，只需执行本步并在 AGENTS.md 保留路由节。

**要解决的问题**：多个 Agent 共享同一工作树时，未提交修改互相可见、`git add`/commit 的 index 竞争、半成品互相污染。git worktree 隔离未提交文件与 index；合入、语义与外部状态冲突仍需协调。helper 提供跨 Agent 宿主的本地协作入口，但不拦截任意写入或手动 Git 操作。

安装：复制 assets/scripts/worktree_task.py 到 scripts/；另获授权时安装 assets/hooks/reference-transaction.sh。若使用 pre-commit 框架，不能声称其会自动执行 reference-transaction；按实际 hook 接线验证，避免替换已有 hooksPath。canonical 非默认分支时用 git config worktree-task.canonicalRef 明确指定。

安装后按 workflow-patterns.md「工具支持」读取唯一详细 CLI 契约，验证 create → intent → review → coordinate（相关任务）→ admit → check --write → integrate → close → cleanup。实际参数以 helper --help 为准；先核实主工作树 claim。未知范围不冒充协调，失败对象保留，不能凭时间抢锁或删 creating 半状态。
