# 评测治理硬化：eval-baseline 从参考文档升格为治理义务

> 状态：✅ completed（2026-10-27，converge 评议收敛后落地，提交 4693e75）
> 决策来源：Anthropic《How the Claude Code team does code review》的"事故即 eval"机制与 eval-baseline.md 现状对照——体系已涵盖"踩坑的记忆化"（bugfix 一等载体 + 检索硬约束 + 活性追踪），缺"踩坑的考题化"（eval-baseline 是孤儿：SKILL.md 仅 L276 目录树提及，无触发义务、无 fixture 路径、无护栏、pitfalls 无晋升通道）。

## 目标

把"经验累积"接上"评测回放"：bugfix/pitfalls 素材可成为可重放的 eval 案例；治理文档行为面改动被强制度量；eval-baseline 从参考文档升格为带硬约束的治理义务。

## 设计论证

1. **对齐 Anthropic 机制**：事故案例要件 =（现象 + 引入源 + 确认 + 判据）。bugfix.md 已有前三个的字段级对应（evidence 门禁、变更 commit 锚点、verification 字段），缺"可重放"与"必跑"两件。
2. **硬约束靠工具（哲学第 9 条）**：义务只写在 prose 里等于不存在。触发与强制进 audit.py；判分执行由独立 reviewer 承担（跨模型族）；护栏留在体系外部（返工/修正类信号不可刷）。
3. **Goodhart 防御**：硬约束只钉"记了"——eval 记录的存在性可机械验证；"跑了"无法机械验证（fixture 自动重放 runner 本期不做），依赖 reviewer 独立判分与护栏旁路验证。不约束分数好坏；护栏指标人工填写、明确不作优化目标。
4. **最小改动**：pitfalls.md 不做结构重构，晋升走流程通道不靠格式；`pitfalls.md.tpl` 仅在「何时填写」注释块加一行晋升规则。fixture 自动重放 runner 不在本次范围。

## R1/R2 判定语义

### R1（error）：`status: fixed` 必须携带 eval 记录

- 纯机械存在性检查，与 `verification` 字段完全解耦：fixed + manual 的可重放文档不得逃逸；fixed + none 但 eval 块齐备不误报；`skipped` 不构成 verification 缺失的挡箭牌。
- 判据：frontmatter 携带平面 eval 键组（形态见下）**或** `eval: skipped` + `eval_skip_reason`，二者缺一 → error。
- Grandfathering：仅对 `created_at >= 2026-10-27` 的文档生效（bugfix 模板已有 created_at 字段，机械可判定）；存量文档豁免。
- 扫描范围：`docs/problems/bugfix/*.md`，排除 `_template.md`；目录不存在 → no-op。
- `created_at` 缺失或非 `YYYY-MM-DD` 格式（含占位符 `[YYYY-MM-DD]`）→ 视为豁免，并出 warn 提示补字段。

### eval 块形态（平面键，钉死）

- `audit.py` 的 `_parse_frontmatter` 是缩进盲的平面解析器：嵌套块被摊平、行内 `#` 注释被剥除。eval 块禁用嵌套，钉死为单键 + 平面前缀键：`eval: skipped|scored` + `eval_fixture` / `eval_command` / `eval_expect` / `eval_last_scored` / `eval_score`（可选）/ `eval_skip_reason`。
- per-doc `eval_score` 定位为快照；回归表是唯一权威账本，消双账本漂移。
- 新增键不得含 git/commit 英文词（no-git 投影测试对模板有 `\bcommit\b` 级禁用正则）。

### R2（warn → error）：行为面改动强制度量

- **行为面清单**（plan 内显式枚举，不复用 GOV_PATTERNS 作单一事实源——该名单在仓库有 5 处定义、2 套内容（`.githooks/pre-commit` 与 `assets/hooks/pre-commit-{python,node,go,generic}.sh` 各异），运行时解析不成立）：`SKILL.md`、`README.md`、`assets/templates/zh/**`、`assets/references/*.md`（不含 `eval-baseline.md`——账本自身不入被考对象，否则每次记分制造下一次违规）。排除 `assets/scripts/**`、`assets/hooks/**`、`.githooks/**`：由 pytest 门控，不入 eval 义务——eval-baseline 度量的是 skill 产出质量，脚本与 hook 改动不改变产出，强行记分是 Goodhart 诱因；此即本清单与 GOV_PATTERNS 的取舍差异及理由。
- **激活门**：`assets/references/eval-baseline.md` 存在且仓库存在 `.git`，二者齐备才激活；否则该检查 status=skip 并输出提示。账本存在即考、无账本不考——生成项目不下发 eval-baseline.md，天然豁免，与兼容口径「只对 skill 仓库自身生效」互为印证。
- **状态来源 = git**：anchor = 最近一次触碰 eval-baseline.md 回归区的 commit；统计 anchor 之后触碰行为面文件的 commit 数，≥1 → warn，≥2 → error。"行为改动与记分同一 commit"时该 commit 即新 anchor，语义自洽。
- 「回归区触碰」= commit diff 中 eval-baseline.md 有以行首 `|` 起始的新增/删除行（表行级判定，护栏小节的纯文字修订不重置计数）。
- **空表 skip**：「空表」= 不存在「版本 / commit」列匹配完整 40 位十六进制 SHA 的数据行（现占位行"当前 main"不算记录）；空表 → skip（skip-until-first-record）；bootstrap 由 C4 写入首条基线行，commit 自点火问题随之消解。
- **no-Git profile**：R2 整体 skip 并输出提示。无 mtime 兜底——SKILL.md 哲学 10 与 maintain.py 已明确否决 mtime 驱动的治理文档检查，不复活。

### warn 不阻塞：退出码语义

- `_cmd_check` 退出容忍集合从 `ok/found/skip` 扩为 `ok/found/skip/warn`；error 仍退出 1。
- 既有 line_budget（AGENTS.md 超限）随容忍集合扩含 warn，从「退出 1」变为「提示放行」——机制既定副作用，接受之。
- 本仓 pre-commit 只跑 pytest；audit 的消费面是 maintain.py --check 与人工运行。

### L1 记分粒度

- 允许范围化记分（如 `L1 partial: scope=medium-git`），防"为消警而全量空跑"的形式合规。
- `eval: skipped` 的比率作为噪音指标记入回归表（对应 Anthropic 机制的误报率腿）。

## 变更范围

| 层 | 变更 |
|---|---|
| C1 模板 | `assets/templates/zh/bugfix.md.tpl`：frontmatter 增加可选平面 eval 键组（形态钉死见「R1/R2 判定语义」）；注释块写明强制判据——`status → fixed` 必带 eval 键组或 `skipped`+理由；复现方式为 agent 可重放操作序列 → scored，纯环境/硬件类不可重放故障 → skipped+理由；per-doc `eval_score` 注明为快照、回归表为唯一权威。`assets/templates/zh/pitfalls.md.tpl`：「何时填写」注释块加一行晋升规则——同一坑位再次实际踩到且当时未建档案 → 升格补写 bugfix 档案；注释不得出现字面量 `assets/references/`（会打红 `test_generated_templates_do_not_link_to_skill_internal_assets`）。`frontmatter-schemas.md.tpl` 经核不载 bugfix 字段，无需同步 |
| C2 审计 | `assets/scripts/audit.py` 新增 R1（error）/ R2（warn→error）两条检查，判定语义见「R1/R2 判定语义」；`_cmd_check` 退出容忍集合扩为 `ok/found/skip/warn`；`_format_text` 为新检查 kind 加分支（缺分支则文本模式静默吞行，只 `--json` 可见）；SKILL.md L272「~15 项」与 L235 audit.py 简介随本项顺手同步 |
| C3 SKILL.md + README.md | 按受众拆分。① `SKILL.md` 记忆系统段——pitfalls 晋升通道，插入位置在列表末项（L201 规模裁剪）之后、收束段（L203）之前（列表实际延续到 L201，插在 L199 后会切开列表）；衔接 L198 既有「晋升候选」概念；机制 = "判断即触发、升格动作即记录"，明示软约束、由修复该问题的 agent 判断，不假装机械触发；不新增编号标题（本变更走 ultraverge 范围、准则段克制 + Occam，非测试约束——`test_skill_guidance.py` L405 只锁哲学 12 标题原文，拦不住新增"### 13."）；文风对齐 L194-201。② `README.md` 维护指引——本仓自身评测义务（行为面改动提交前必跑 L1 并在回归表记分，L2/L3 按触达面裁量：frontmatter description → L2，模板产出物 → L3）+ eval-baseline.md 为评测唯一权威；衔接 README L153「同一教训再次遭遇 → 重新走收录判据」先例通道；SKILL.md 最多留一句指针指向 README |
| C4 评测基线 | `assets/references/eval-baseline.md`：回归记录表加「日期」「护栏」「记分来源」三列（表头/分隔行/占位行三处同步）；「版本 / commit」列规格化为完整 SHA + YYYY-MM-DD；新增「护栏指标」小节（定义：任务返工率、用户修正次数等体系外信号；采集：会话复盘与用户反馈；Goodhart 说明：只作对冲信号、不作优化目标——定义/采集/说明不因扩列改动）；记分行承载范围化 L1 记分与 skipped 率噪音观测；写入首条基线行（bootstrap，记分来源 = 本次 converge 评议），R2 空表 skip 随之自点火；`test_eval_baseline_covers_absorbed_init_behaviors`（test_skill_guidance.py）钉了评估哲学/测试矩阵两段的 8 个字符串，扩列时不得触及那两段 |
| C5 测试 | `tests/test_audit.py`：R1 用例（fixed 无 eval 记录 → error；`skipped`+理由 → 通过；`created_at` 早于 2026-10-27 → 豁免）；R2 用例（临时 git 仓库 fixture——test_audit.py 现为 Git-free 契约，此为测试前提的显式扩充；anchor 后 1 个行为面 commit → warn，≥2 → error；空表 → skip；触碰回归区（表行）的 commit 重置计数；反例：只改护栏小节散文 → 不重置）；`_cmd_check` 退出码断言按新容忍集合；`_format_text` 新 kind 分支覆盖。落地前全量基线：92 tests 全绿（`python -m unittest discover -s tests` 约 280s；本机默认 python 无 pytest，`.githooks/pre-commit` 用 `python -m pytest tests/ -q` 做门禁） |

## 兼容与迁移口径

- 生成项目侧：存量 bugfix 文档无 eval 块——R1 按 created_at grandfathering，无追溯杀伤；R2 本期只对 skill 仓库自身生效，不给生成项目装行为面度量（留待实证需求）
- no-Git profile：R1 不变（纯 frontmatter 存在性检查）；R2 整体 skip 并输出提示，无 mtime 兜底；bugfix 模板新增 eval 键组不含 git/commit 词，no-git 投影测试不受影响
- `eval: skipped` 必须附 `eval_skip_reason`，堵规避口；skipped 率入回归表作噪音观测，防 skipped 滥用
- warn 不阻塞退出码（容忍集合扩为 `ok/found/skip/warn`）：maintain.py --check 对 warn 由非 0 变为放行，error 判定不变

## 明确不做

- fixture 自动重放 runner（L1 自动化增强另立计划）
- L2/L3 自动化与 CI 引入（本仓无 CI）
- 生成项目侧 R2；生成项目侧 eval-baseline 资产下发
- `assets/scripts/**` 纳入行为面（由 pytest 门控，不入 eval 义务）
- mtime 驱动的行为面检测（已被哲学 10 否决，不复活）
- pitfalls.md.tpl 结构重构（C1 只动「何时填写」注释块，不动正文结构）

## 验证

- `python -m pytest tests/ -q` 全绿（基线 92 tests；本机默认 python 无 pytest 时用 `python -m unittest discover -s tests`，约 280s）
- audit.py 行为自检：临时构造违规样例，验证 R1 error / skipped+理由通过 / R2 warn→error / 空表 skip / no-Git skip 提示
- `--json` 与文本两种输出模式各跑一遍，确认新 kind 不被 `_format_text` 静默吞行
- 全仓 grep 无死链；SKILL.md 新段不新增编号标题、与记忆系统列表文风一致；README 维护指引与 L153 路由表口径一致
- eval-baseline 回归表含首条基线行，日期/护栏/记分来源三列齐备

## 复查记录

- 本变更触及治理文档（SKILL.md），按触发边界走 ultraverge 级 converge：R1 三独立 Reviewer 评议（12 条规格意见）→ Executor 修订 → R2 双 Reviewer 验收（收敛出 R2 行为面显式清单与激活门两处规格洞）→ Executor 定点修订 → Delta Reviewer 判可执行 → 盲审复核判可执行（blind_recheck: pass）→ 强制设计审查（10 条 advisory，处置见归档 retrospective）。全程档案：`.converge/done/20261027-eval-governance-hardening/`（本地，不入库）。
- 落地结果：7 文件 +527/-10，测试 92→117 全绿（+25 新用例），单提交 4693e75。落地期四处实现级偏差（ROOT 解析扩展、anchor 经 git log 重算的等效形态、R1 scored 态最小校验、plan emoji 状态观察项）已在收敛档案 attempts.md 落地段记录。
- 遗留：fixture 自动重放 runner、L2/L3 自动化与 CI、生成项目侧行为面度量——见「明确不做」，凭实证另立计划。
