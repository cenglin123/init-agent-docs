# 初始化操作参考

本文件按阶段读取，模板仅在生成对应资产时读取。沿用入口的路径、profile、KB 与授权约束。

## 调查与选项

1. 先检查 .git 是否存在（目录或指针文件），不为探测 no-Git 执行 Git。Git 读取当前分支、remote、upstream 和工作树状态，按真实 upstream 比较；未配置 upstream 就说明无法比较，不猜 origin/main。有修改先核实归属，不自动清理、stash、commit、pull 或 push。
2. 按已知画像选择 profile，广泛调查/迁移前先建立起始检查点：Small 用 docs/initialization.md；中大型用 docs/plans/active/initialization.md。状态含 status: in_progress、repository_mode（git | no-git）、size（small | medium | large）、已授权范围、来源、当前阶段、完成/未完成产物、核实事实及精确出处、约束迁移、取舍/未决、下一步/须读分区、验收证据；尚未核实的事实如实留未决。CURRENT 仅指状态与下一步，不重复阶段清单。阶段末覆盖当前状态，不无限追加流水。新记录的 status 只写 in_progress | done | cancelled；初始化验收前用 in_progress，通过后才用 done。字段值用上述小写枚举，合法标量可带成对引号；size 不写合并标签或中文别名。
3. 调查 README*、manifest、workspace、lockfile、task runner、lint/format/typecheck/codegen、CI。命令及顺序以可执行事实为准；必要时读少量入口，不随机遍历叶子文件。
4. 覆盖前分批核对旧 AGENTS.md、CLAUDE.md、GEMINI.md、.cursor/rules/**、.cursorrules、.github/copilot-instructions.md、opencode.json/jsonc、.opencode/opencode.json。记录已核/未核范围，保留硬约束、禁止事项、命令与单包验证、模块边界、用户定制的精确出处、条件作用域与迁移去向；不要求单个上下文全部读完。信息归口冲突按职责去重，事实内容冲突按事实源裁决；未决冲突不得静默丢弃。
5. 澄清用途、工具链、约束、已有文档、产物路径、测试、协作倾向、常见任务与语言。仓库能回答的不问用户。规模、覆盖旧入口、hooks 等可选项使用已有授权；不足时只问关键缺口。规模按真实复杂度选，不以文件数硬分类；Git 能力是独立轴，不自动 git init。画像变化在检查点修正 profile 与去向。

来源记录：Git 来源记经核实 HEAD 和 dirty/clean/unknown；未提交源码不能只用 HEAD 冒充完整版本。记录实际采用的入口、组件/模板标识及哈希。生成文档保留语义填写后的生成基线位置/哈希，须能实际取回正文，哈希本身不是基线；仅保存实际交付且预期升级的组件基线，放初始化记录旁，或引用可检索的精确版本，不重复复制整套源模板，不写源绝对个人路径。无法取得版本如实 unknown。

## 最小入口与迁移

1. 读 AGENTS、README、CURRENT 模板。先完成项目用途、硬约束、真实验证命令与恢复入口，创建一个能安全接手的最小 AGENTS；不存在的专题先不导航。
2. 所有规模复制 assets/scripts/{changelog,audit,check_all}.py 到目标 scripts/；KB 按入口契约投影路径。确认目标已有同名文件的定制后再合并，不能直接覆盖。
3. 创建/更新 README（已有则保留人类入口与定制）、docs/CURRENT.md、docs/CHANGELOG.md，后者用 changelog 模板作空壳再由 add 写首条。Small 任务/交接内联 CURRENT，初始化进度仍只在出生档案。
4. 旧行为约束归 AGENTS；设计原因归实际已选专题，Small 短内容内联。API/部署/陷阱按需要归相应专题；从代码可直接推导的重复清单删除。核对迁移完整性后删除旧入口副本与已迁空文档，不留弃用标注，历史写 CHANGELOG；no-Git 用文件系统删除。不要把不属于入口副本的工具配置整个删除，只移除已归口规则并保留其他设置。
5. 清退遗留同步机制：删除 scripts/agent_links.py，移除旧 hook/pre-commit 配置中的同步调用，保留独立技术栈检查；no-Git 不执行 Git-only 操作。
6. 阶段末更新状态的迁移清单与下一步。大型文档逐模块迁移，不先把整库读入上下文。

## 扩展资产

### 所有规模

生成 docs/audit-checklist.md，按下述 profile 条件块投影后按实际生成资产裁剪全文，检查链接、反引号路径、纯文本和命令；不能只删链接。模板注释删除，脚本消费的 memory-index 标记保留。保留 CHANGELOG 的 titles/show/add/recent 局部操作与不读全文约束，以及治理修改默认一次独立视角审查、遵从项目已有更严格要求及结论记录口径；不复制来源仓的 ultraverge/盲评标定。候选状态/证据/验证/拒绝/观察及债务/审计纯记录编辑豁免，改变规则不豁免。审计清单候选/债务段均在「审计记录」前，普通局部核对不得向审计记录写日期销警。

Small：不建 STRUCTURE、overview、deployment、plans、memory、maintain 或 governance 专题。AGENTS 内联文件治理简短规则；「治理闭环」从 governance-contract.md 的 small-contract 标记段提取，不手维护第二份。审计清单删所有中大型资产指引，业务待办绑定 CURRENT，候选绑定清单。完工命令为 python scripts/check_all.py --quiet --small；定期审计 python scripts/audit.py check。导航包含 CURRENT、CHANGELOG、audit-checklist、initialization。

### 中型与大型

- 生成 STRUCTURE、overview、deployment、plans/active 与 completed、problems/bugfix/_template.md；API、pitfalls、frontmatter-schemas 有需求才建。Large 按模块拆分但不预建空计划。
- 将 governance-contract.md 复制为 docs/governance.md；删除 Small 投影节（不在专题重复该摘要），AGENTS 导航指向 docs/governance.md，STRUCTURE 索引使用 governance.md 相对链接。详细文件治理唯一位于 STRUCTURE「文件治理」，AGENTS 只留指针。
- 从 MEMORY/user-role 模板生成 .agents/memory/MEMORY.md 与 user/role.md，填已知信息（未知如实说明，不臆造用户画像）；AGENTS 内联摘要及检索入口。启动/恢复/查重默认用 maintain.py --memory-search "关键词" --limit 5，覆盖全部记忆与 bugfix 分区；按命中链接读原文，完整 MEMORY 索引按需读取，未命中如实说明。
- 复制 maintain.py，运行 python scripts/maintain.py --memory-index。索引段覆盖记忆与 bugfix，禁止手改；逐篇 bugfix 不登记 STRUCTURE，只登记目录。日常 python scripts/maintain.py，--check 只读。KB docs_maintain.py 委托 memory_index.py，不写第二索引。
- Bugfix 有可复用教训、复发、高风险或用户要求才按 _template.md 留专篇，其余用现有任务/CHANGELOG 留必要验证；同根因再犯修订原文档。默认实际验证证据留档，仅项目明确使用重放时填写 eval。命中经验并实际遵循才更新 last_confirmed/confirmed_count，不能为年龄消警 touch。经验写入、修改、移动或删除后，同一任务用 --memory-index 刷新派生入口，不要求全量维护审计；活性/审计年龄由维护器提示。
- 按生成资产更新 AGENTS、STRUCTURE、README、CURRENT、审计清单；可选文档没有生成则相关操作指引也删。普通复杂任务按需创建计划，初始化计划仍是自己的唯一进度源。

### 条件块投影

模板使用 Small / Medium/Large 与 Git / no-Git profile only 成对注释。选择一个 size 和 repository_mode，保留匹配块、删除不匹配块，再删除生成指导注释。不同轴可以嵌套，必须正确配对；随后语义填写并检查实际存在性。Small/no-Git 不得残留其他 profile 的纯文本命令或指引。

只在授权选择时读 optional-integrations 对应节；不要为了全套而安装 hooks、插件或 worktree。

### 已有项目升级

按「旧生成基线 / 项目当前版本 / 新源组件」三方比较。先标记本地定制与上游变化，冲突由 Agent 依据现事实裁决，保留用户定制和硬约束，再验收。只有源模板不是旧生成基线；基线不可取时不得假装自动合并，重新调查当前约束、给差异迁移并说明不确定性。上游新修订不自动改变下游规则，不开发通用自动升级服务。

## 验收与交付

1. 按选定 profile 检查实际产物、README、导航、结构索引、初始化状态与源基线。AGENTS 非空 ≤250 行，命令有事实出处；不链接尚未生成文件；逐项对照 AGENTS 模板核实 CHANGELOG 局部操作和治理独立复查合同仍在入口可发现，生成基线正文可按记录位置实际取回。
2. 用 python scripts/changelog.py add --title "初始化文档体系" --body "范围、迁移去向与初始化记录入口" 写首条，再 titles --limit 5 确认。no-Git 仍可运行文档脚本。
3. 运行 python scripts/audit.py check 和 python scripts/check_all.py --quiet（Small 加 --small）；中大型运行 audit.py memory、maintain.py --memory-index 后 maintain.py --check。KB 替换实际路径/维护器名。维护器会检查出生档案，进行中的初始化状态必须已存在。
4. 检查所有生成 Markdown 无死链、指导注释或未填方括号；可执行占位/写作模板与 memory-index 脚本标记按用途识别，不误删。Small 不得有 STRUCTURE/overview/memory/plans/maintain 指引；no-Git 不得有 Git-only 行为。API/pitfalls/schema 未生成时清理相应指引。
5. 必须交独立新上下文/Agent 仅先看目标 AGENTS，回答：项目做什么、不能改什么、完工做什么、复杂任务先去哪；再按必要导航核查真实文件/命令。含糊、错误或硬约束丢失则返工，执行者自检不替代此关。沿用既有控制器，无控制器则由项目本地合同完成独立检查；不强制安装 converge。初始化和普通项目后续规则修改默认一次独立视角检查，遵从目标已有更严格要求。
6. 所有必需检查和独立验收通过才置 status: done：Small 在 docs/initialization.md 原地留出生档案，不被普通任务覆盖；中大型移到 docs/plans/completed/initialization.md，修正 CURRENT 链接并复跑链接检查。记录实际证据与未跑项，不提前报告完成。
7. 报告 profile、产物、裁剪/迁移、检查、独立验收和未决项；明确源码/发布/部署边界。测评本 Skill 时 L1 实物和 L1.5 合成树分开，L2/L3 未跑不宣称因果收益。
