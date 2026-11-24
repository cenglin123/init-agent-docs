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

   **路径 A：直接复制通用或按栈参考 hook 示例到 `.githooks/pre-commit`**（优先复用项目已有 task runner / lint 命令，不强套默认模板）

   - 通用骨架（推荐首选，自行接入项目已有 lint/test 命令）→ `assets/hooks/pre-commit-generic.sh`
   - 按栈参考示例：Python → `assets/hooks/pre-commit-python.sh`、Node/TS → `assets/hooks/pre-commit-node.sh`、Go → `assets/hooks/pre-commit-go.sh`

   ```bash
   mkdir -p .githooks
   cp assets/hooks/pre-commit-generic.sh .githooks/pre-commit   # 或选用按栈参考示例
   chmod +x .githooks/pre-commit
   git config core.hooksPath .githooks
   ```

   **Windows 注意**：Bash hook 需 Git Bash 解释；纯 PowerShell 或跨平台多语言项目优先改用路径 B 的 `pre-commit` 框架。

   **路径 B：使用 `pre-commit` 框架（跨平台 / 多语言项目推荐）**

   复制 `assets/hooks/pre-commit-config.yaml` 到 `.pre-commit-config.yaml`，按项目实际栈解开注释后运行 `pre-commit install`（与路径 A 互斥，不叠加 `core.hooksPath`）；记忆结构兜底与治理提醒按需以 local hook 补充。


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

安装后按 workflow-patterns.md「工具支持」核对 CLI 契约，验证 `claim-main` / `create` / `check` / `integrate` / `cleanup` / `list` / `release-main`。实际参数以 `python scripts/worktree_task.py --help` 为准；外包施工优先留 diff 验收后再统一 commit 与 integrate，失败对象保留，不凭时间抢锁。

## Python 静态结构图谱（默认跳过）

**触发条件**：Python 项目需要离线或无稳定语言服务（LSP）时的可复验静态结构证据（不依赖 Git），且用户明确授权安装。默认初始化不复制该脚本，避免为不需要的项目预付维护成本（Occam）。

- **安装**：复制 `assets/scripts/repo_graph.py` 到目标 `scripts/`（KB 按入口路径契约投影到 `.meta/scripts/`）。复制脚本本身不创建 `.agents/repo-graph/`。
- **使用与验证**（KB 按入口路径契约替换为 `.meta/scripts/` 与 `docs_maintain.py`）：
  - 未建图时运行 `python scripts/repo_graph.py check` 验证安装副本（返回 `not_initialized`，不创建图）。
  - 需要结构证据时显式运行 `python scripts/repo_graph.py build` 生成 `.agents/repo-graph/`；用 `python scripts/repo_graph.py show --path <项目相对路径或对象ID>` 与 `python scripts/repo_graph.py impacted --paths <路径或对象ID> [...]` 做有界渐进查询。
  - `.agents/repo-graph/manifest.json` 存在后，`audit.py check` 自动做只读校验（过期报 warn、损坏报 invalid），`maintain.py` 自动刷新已有图，`maintain.py --check` 只读校验已有图；`.agents/repo-graph/manifest.json` 不存在时两者静默跳过；若保留 manifest 但缺失脚本，两者均 fail-closed 报 `invalid`（恢复脚本或移除 `.agents/repo-graph/`）。
- **边界**：仅提供 Python AST 静态结构证据（`direct` / `inferred` / `external` / `unknown`），不是运行时调用图，也不生成 AOCI Baseline 或 F/R/A/S 语义。
