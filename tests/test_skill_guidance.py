"""Contract checks exercise routing and profile projection, never concatenate references."""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")

def project_profile(text: str, mode: str, size: str = "medium", *, remove_guidance: bool = True) -> str:
    stack = []
    lines = []
    choices = {"Git": mode == "git", "no-Git": mode == "no-git",
               "Small": size == "small", "Medium/Large": size != "small"}
    for line in text.splitlines():
        match = re.fullmatch(r"<!-- (/)?(Git|no-Git|Small|Medium/Large) profile only -->", line.strip())
        if match:
            close, kind = match.groups()
            if close:
                if not stack or stack.pop() != kind:
                    raise AssertionError("unbalanced profile block: " + kind)
            else:
                stack.append(kind)
            continue
        if all(choices[k] for k in stack):
            lines.append(line)
    if stack:
        raise AssertionError("unclosed profile blocks")
    if not remove_guidance:
        return "\n".join(lines)
    return re.sub(r"<!--.*?-->", lambda m: m.group(0) if re.fullmatch(r"<!-- memory-index:(?:start|end) -->", m.group(0)) else "", "\n".join(lines), flags=re.DOTALL)

def project_repository_mode(text: str, mode: str) -> str:
    return project_profile(text, mode)

def execution_instruction_bytes(root: Path) -> int:
    paths = [root / "SKILL.md"] + sorted(p for p in (root / "assets/references").glob("*.md") if p.name != "eval-baseline.md")
    return sum(p.stat().st_size for p in paths)

class SkillGuidanceTestCase(unittest.TestCase):
    def assert_contains_all(self, text, expected):
        for item in expected:
            self.assertIn(item, text)

    def test_entry_is_bounded_and_routes_each_phase(self):
        entry = read_repo_file("SKILL.md")
        self.assertLessEqual(len(entry.splitlines()), 200)
        self.assertLessEqual(len(entry.encode("utf-8")), 24576)
        for section in ("调查与选项", "最小入口与迁移", "扩展资产", "验收与交付"):
            self.assertIn(section, entry)
            ref = read_repo_file("assets/references/initialization.md")
            self.assertIn("## " + section, ref)
        self.assertIn("只读取当前阶段", entry)
        self.assertIn("不重读全库或全部参考", entry)
        self.assertNotIn("不必节省篇幅", entry)
        self.assertNotIn("### 第 6", entry)
        for link in re.findall(r"\]\((assets/[^)]+)\)", entry):
            self.assertTrue((REPO_ROOT / link).exists(), link)
        self.assertLess(execution_instruction_bytes(REPO_ROOT), 101037)

    def test_additional_reference_is_included_in_instruction_budget(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references = root / "assets/references"
            references.mkdir(parents=True)
            (root / "SKILL.md").write_bytes(b"entry")
            (references / "initialization.md").write_bytes(b"phase")
            (references / "eval-baseline.md").write_bytes(b"excluded ledger" * 100)
            baseline = execution_instruction_bytes(root)
            extra = b"new execution reference"
            (references / "new-partition.md").write_bytes(extra)
            self.assertEqual(execution_instruction_bytes(root), baseline + len(extra))

    def test_entry_profiles_preflight_and_kb_contract_are_directly_reachable(self):
        entry = read_repo_file("SKILL.md")
        table = entry.split("## Profile 摘要", 1)[1].split("## 分阶段读取", 1)[0]
        for name in ("Small + Git", "Small + no-Git", "Medium/Large + Git", "Medium/Large + no-Git"):
            self.assertIn("| " + name + " |", table)
        self.assertIn("no-Git 不运行 Git", entry)
        self.assertIn("不自动 init", entry)
        kb = entry.split("## 知识库叠加时的路径契约", 1)[1].split("## 完成判据", 1)[0]
        for name in (".meta/scripts/", ".meta/memory/", "docs_maintain.py", "memory_index.py", "不创建第二索引写入者"):
            self.assertIn(name, kb)
        investigation = read_repo_file("assets/references/initialization.md").split("## 调查与选项", 1)[1].split("## 最小入口", 1)[0]
        for name in ("small | medium | large", "git | no-git", "in_progress | done | cancelled"):
            self.assertIn(name, investigation)
        self.assertIn("不为探测 no-Git 执行 Git", investigation)
        self.assertIn("哈希本身不是基线", investigation)

    def test_generation_and_acceptance_preserve_behavior_contracts(self):
        ref = read_repo_file("assets/references/initialization.md")
        expansion = ref.split("## 扩展资产", 1)[1].split("## 验收与交付", 1)[0]
        acceptance = ref.split("## 验收与交付", 1)[1]
        for term in ("titles/show/add/recent", "不读全文", "冻结基线盲评", "≥3 独立视角", "结论记录"):
            self.assertIn(term, expansion)
        self.assertIn("CHANGELOG 局部操作和治理盲评标定", acceptance)
        self.assertIn("基线正文", acceptance)
        template = project_profile(read_repo_file("assets/templates/zh/AGENTS.md.tpl"), "no-git", "medium")
        self.assertIn("**记忆自检**", template)
        self.assertIn("MEMORY.md「确认 touch」", template)
        self.assertIn("titles/show/add/recent", template)
        self.assertIn("只给冻结基线", template)

    def test_current_eval_method_covers_all_small_deliverables(self):
        ledger = read_repo_file("assets/references/eval-baseline.md")
        method = ledger.split("## 测试项目矩阵", 1)[1].split("## L2：", 1)[0]
        for path in ("README.md", "docs/audit-checklist.md", "docs/initialization.md", "scripts/changelog.py", "scripts/audit.py", "scripts/check_all.py"):
            self.assertIn(path, method)
        self.assertIn("### Small 额外项", method)
        self.assertIn("所有 profile 的出生档案", method)
        self.assertIn("context-bounded-l1-v2", ledger.split("## 测试项目矩阵", 1)[0])

    def test_investigation_and_migration_have_single_operation_source(self):
        ref = read_repo_file("assets/references/initialization.md")
        investigation = ref.split("## 调查与选项", 1)[1].split("## 最小入口", 1)[0]
        for term in ("manifest", "CI", ".cursor/rules/**", ".github/copilot-instructions.md",
                     "opencode.json", "精确出处", "已有授权", "dirty/clean/unknown", "生成基线"):
            self.assertIn(term, investigation)
        migration = ref.split("## 最小入口与迁移", 1)[1].split("## 扩展资产", 1)[0]
        self.assertIn("不存在的专题先不导航", migration)
        self.assertIn("agent_links.py", migration)
        self.assertIn("不留弃用标注", migration)
        self.assertIn("不能直接覆盖", migration)

    def test_small_projection_removes_inapplicable_plain_instructions(self):
        forbidden = ("STRUCTURE", "overview", ".agents/memory", "MEMORY.md", "plans/",
                     "maintain.py", "governance.md", "worktree")
        for name in ("AGENTS", "audit-checklist", "CURRENT", "README"):
            template = read_repo_file("assets/templates/zh/" + name + ".md.tpl")
            for mode in ("git", "no-git"):
                text = project_profile(template, mode, "small")
                for term in forbidden:
                    self.assertNotIn(term, text, name + ": " + term)
        self.assertIn("--small", project_profile(read_repo_file("assets/templates/zh/AGENTS.md.tpl"), "no-git", "small"))

    def test_governance_projection_has_single_source_and_double_navigation(self):
        contract = read_repo_file("assets/references/governance-contract.md")
        small = contract.split("<!-- small-contract:start -->")[1].split("<!-- small-contract:end -->")[0].strip()
        template = read_repo_file("assets/templates/zh/AGENTS.md.tpl")
        self.assertNotIn(small, template)
        self.assertIn("small-contract", template)
        for term in ("冻结基线", "独立验收", "保留任务", "停止条件", "外部副作用", "失败不晋升"):
            self.assertIn(term, small)
        for mode in ("git", "no-git"):
            agents = project_profile(template, mode)
            structure = project_profile(read_repo_file("assets/templates/zh/STRUCTURE.md.tpl"), mode)
            self.assertIn("](docs/governance.md)", agents)
            self.assertIn("](governance.md)", structure)
        for text in (contract, contract.split("## Small 最小投影")[0]):
            self.assertIsNone(re.search(r"(?i)\bgit\s|\bcommit\b|\bworktree\b|assets/references/|docs/plans", text))

    def test_selected_utf8_pitfalls_respect_no_git_before_comment_cleanup(self):
        pitfalls = read_repo_file("assets/templates/zh/pitfalls.md.tpl")
        no_git = project_profile(pitfalls, "no-git", "medium", remove_guidance=False)
        git = project_profile(pitfalls, "git", "medium", remove_guidance=False)
        self.assertIn("## UTF-8 编码", no_git)
        self.assertIn("### 终端与 Shell", no_git)
        self.assertNotIn("### Git 与中文路径", no_git)
        self.assertNotIn("git config", no_git)
        self.assertIn("git config --global core.quotepath false", git)
        rendered = project_profile(pitfalls, "no-git", "medium")
        self.assertIn("encoding='utf-8'", rendered)
        self.assertNotIn("git config", rendered)
        bugfix = read_repo_file("assets/templates/zh/bugfix.md.tpl")
        self.assertNotIn("git log", project_profile(bugfix, "no-git", remove_guidance=False))
        self.assertIn("git log", project_profile(bugfix, "git", remove_guidance=False))
        for text in (pitfalls, bugfix):
            in_comment = False
            for token in re.findall(r"<!--|-->", text):
                if token == "<!--":
                    self.assertFalse(in_comment, "nested HTML comment")
                    in_comment = True
                else:
                    self.assertTrue(in_comment, "closing unopened HTML comment")
                    in_comment = False
            self.assertFalse(in_comment, "unclosed HTML comment")

    def test_small_readme_navigation_and_governance_notice_contract(self):
        readme = project_profile(read_repo_file("assets/templates/zh/README.md.tpl"), "no-git", "small")
        for target in ("docs/audit-checklist.md", "docs/initialization.md"):
            self.assertIn("](" + target + ")", readme)
        agents = project_profile(read_repo_file("assets/templates/zh/AGENTS.md.tpl"), "no-git", "medium")
        self.assertIn("高风险改动必须", agents)
        self.assertNotIn("高风险改动优先", agents)
        schema = read_repo_file("assets/templates/zh/frontmatter-schemas.md.tpl")
        self.assertIn("仍放在 `active/`", schema)
        self.assertIn("不因年龄失败", schema)
        plugin = read_repo_file("assets/plugins/governance-watch.js")
        self.assertIn("optional-integrations.md「会话级治理提醒」", plugin)
        self.assertIn("获得提交授权时再提交", plugin)
        self.assertNotIn("完成变更须 git 提交", plugin)
        for old_default in ("oa-ecology-cube", "WORKFLOW", "第 6.4 步"):
            self.assertNotIn(old_default, plugin)
        for placeholder in ("<project-root>", "<governed-path>", "<entry-file>"):
            self.assertIn(placeholder, plugin)

    def test_recovery_and_birth_record_are_not_current_task_state(self):
        ref = read_repo_file("assets/references/initialization.md")
        for term in ("status: in_progress", "docs/plans/active/initialization.md", "status: done",
                     "docs/plans/completed/initialization.md", "旧生成基线 / 项目当前版本 / 新源组件",
                     "基线不可取", "独立验收通过才"):
            self.assertIn(term, ref)
        current = project_profile(read_repo_file("assets/templates/zh/CURRENT.md.tpl"), "no-git", "small")
        self.assertIn("不重复阶段清单", current)
        self.assertIn("不被普通任务覆盖", current)
        self.assertIn("docs/initialization.md", current)

    def test_review_boundaries_and_local_self_maintenance_are_discoverable(self):
        principle = read_repo_file("assets/references/design-principles.md")
        for term in ("ultraverge", "≥3 Reviewer", "标准 converge", "初始化豁免", "严格盲评", "同上下文/同模型", "fail-closed", "逃生舱"):
            self.assertIn(term, principle)
        own = read_repo_file("AGENTS.md")
        self.assertIn("python -X utf8 -m pytest tests/ -q", own)
        self.assertIn("assets/scripts", own)
        self.assertIn("治理合同", own)
        hook = read_repo_file(".githooks/pre-commit")
        self.assertIn(r"^AGENTS\.md$", hook)
        script = read_repo_file("assets/scripts/audit.py")
        self.assertIn('"AGENTS.md",', script)

    def test_memory_and_optional_capabilities_remain_available_on_demand(self):
        ref = read_repo_file("assets/references/initialization.md")
        self.assert_contains_all(ref, ["--memory-index", "索引", "bugfix 分区", "docs_maintain.py", "memory_index.py"])
        memory = read_repo_file("assets/templates/zh/MEMORY.md.tpl")
        self.assert_contains_all(memory, ["memory-index:start", "memory-index:end", "禁止手工编辑", "confirmed_count"])
        projected_memory = project_profile(memory, "no-git", "medium")
        self.assertIn("<!-- memory-index:start -->", projected_memory)
        self.assertIn("<!-- memory-index:end -->", projected_memory)
        optional = read_repo_file("assets/references/optional-integrations.md")
        self.assert_contains_all(optional, ["governance-watch.js", "ENTRY_FILE", "监视路径之外", "默认跳过", "worktree-task.canonicalRef"])
        patterns = read_repo_file("assets/references/workflow-patterns.md")
        self.assert_contains_all(patterns, ["Git common-dir", "同一份协议文本", "head-drift", "partial-state", "unknown"])
        self.assertNotIn("5-10 个文件", patterns)

    def test_single_entry_no_legacy_sync_machinery(self) -> None:
        """单一入口合同：交付面不得再引用已移除的三文件同步机制。"""
        no_agent_links_paths = [
            "assets/hooks/pre-commit-generic.sh",
            "assets/hooks/pre-commit-python.sh",
            "assets/hooks/pre-commit-node.sh",
            "assets/hooks/pre-commit-go.sh",
            "assets/hooks/pre-commit-config.yaml",
            "assets/references/eval-baseline.md",
            "assets/scripts/check_all.py",
            "assets/scripts/maintain.py",
            "assets/scripts/audit.py",
            "assets/templates/zh/AGENTS.md.tpl",
            "assets/templates/zh/README.md.tpl",
        ]
        for path in no_agent_links_paths:
            with self.subTest(path=path):
                text = read_repo_file(path)
                self.assertNotIn("agent_links", text)
                self.assertNotIn("同步声明", text)
                self.assertFalse(
                    (REPO_ROOT / "assets" / "scripts" / "agent_links.py").exists()
                )
        # 入口模板与 hook 不再出现 CLAUDE.md / GEMINI.md（SKILL.md / eval-baseline
        # 中的出现属合法迁移语境：读取旧 instruction 文件并删除副本）。
        no_legacy_entry_paths = [
            "assets/templates/zh/AGENTS.md.tpl",
            "assets/templates/zh/README.md.tpl",
            "assets/scripts/check_all.py",
            "assets/scripts/maintain.py",
            "assets/hooks/pre-commit-config.yaml",
        ]
        for path in no_legacy_entry_paths:
            with self.subTest(path=path):
                text = read_repo_file(path)
                self.assertNotIn("CLAUDE.md", text)
                self.assertNotIn("GEMINI.md", text)

        # 迁移清退语境豁免：SKILL.md 与 audit-checklist 模板允许且仅允许在
        # 「清退遗留同步机制」条目中点名旧产物各一次（可 grep、可执行）。
        skill_text = read_repo_file("assets/references/initialization.md")
        self.assertEqual(len(re.findall(r"agent_links", skill_text)), 1)
        self.assertNotIn("同步声明", skill_text)
        checklist_tpl = read_repo_file("assets/templates/zh/audit-checklist.md.tpl")
        for name in ("agent_links", "CLAUDE.md", "GEMINI.md"):
            with self.subTest(name=name):
                self.assertEqual(len(re.findall(re.escape(name), checklist_tpl)), 1)
        self.assertNotIn("同步声明", checklist_tpl)

    def test_no_git_template_projection_contains_no_git_only_guidance(self) -> None:
        paths = [
            "assets/templates/zh/AGENTS.md.tpl",
            "assets/templates/zh/README.md.tpl",
            "assets/templates/zh/CURRENT.md.tpl",
            "assets/templates/zh/audit-checklist.md.tpl",
            "assets/templates/zh/STRUCTURE.md.tpl",
            "assets/templates/zh/MEMORY.md.tpl",
            "assets/templates/zh/bugfix.md.tpl",
        ]
        forbidden = re.compile(
            r"(?i)(?:\bgit\s+(?:init|fetch|status|log|blame|commit|checkout|restore|"
            r"reset|config|branch|pull|push|clone|worktree|add)\b|origin/main|\.githooks/|"
            r"\bcommit\b|\bworktree\b)")
        for path in paths:
            with self.subTest(path=path):
                rendered = project_repository_mode(read_repo_file(path), "no-git")
                self.assertIsNone(forbidden.search(rendered), rendered)

    def test_generated_templates_do_not_link_to_skill_internal_assets(self) -> None:
        for path in (REPO_ROOT / "assets" / "templates" / "zh").glob("*.tpl"):
            with self.subTest(path=path.name):
                self.assertNotIn("assets/references/", path.read_text(encoding="utf-8"))

    def test_plan_templates_write_canonical_file_status_only(self) -> None:
        plan = read_repo_file("assets/templates/zh/plan.md.tpl")
        schema = read_repo_file("assets/templates/zh/frontmatter-schemas.md.tpl")
        for text in (plan, schema):
            self.assertIn("in_progress | done | cancelled", text)
            self.assertIn("legacy", text.lower())

    def test_pitch_deck_has_balanced_div_tags(self) -> None:
        """Structural assertion: every <div must have a matching </div> in presentation.html."""
        pitch = read_repo_file("assets/pitch/presentation.html")
        opens = pitch.count("<div")
        closes = pitch.count("</div>")
        self.assertEqual(opens, closes,
                         f"Unbalanced div tags: {opens} opens vs {closes} closes")

    def test_bespoke_controller_absent(self) -> None:
        self.assertFalse((REPO_ROOT / "scripts" / "converge_orchestrator.py").exists())

    def test_worktree_task_asset_implements_four_actions(self) -> None:
        text = read_repo_file("assets/scripts/worktree_task.py")
        for action in ("def create(", "def check(", "def integrate(", "def cleanup("):
            with self.subTest(action=action):
                self.assertIn(action, text)
        self.assert_contains_all(
            text,
            [
                "worktree-task.canonicalRef",
                "merge --ff-only",
                "already-integrated",
                "needs-rebase",
                "head-drift",
                "partial-state",
            ],
        )

        hook = read_repo_file("assets/hooks/reference-transaction.sh")
        self.assert_contains_all(
            hook,
            ["prepared", "merge-base --is-ancestor", "worktree-task.canonicalRef"],
        )


    def test_audit_checklist_debt_register_structure(self) -> None:
        checklist_tpl = read_repo_file("assets/templates/zh/audit-checklist.md.tpl")
        self.assertIn("## 未决债务登记", checklist_tpl)
        self.assertIn("已销账", checklist_tpl)
        # 段序铁律：债务段必须在审计记录段之前——maintain.py 的审计触发器
        # 只解析「## 审计记录」之后的窗口，债务条目日期不得进入该窗口
        self.assertLess(
            checklist_tpl.index("## 未决债务登记"),
            checklist_tpl.index("## 审计记录"),
        )

    def test_plugin_stays_light_and_pitch_is_structurally_sound(self):
        plugin = read_repo_file("assets/plugins/governance-watch.js")
        self.assert_contains_all(plugin, ["GOV_REPO", "GOV_PATHS", "ENTRY_FILE", "GOV-DIRTY", "core.quotepath=false"])
        imports = [line for line in plugin.splitlines() if line.strip().startswith("import ")]
        self.assertTrue(imports)
        for line in imports:
            self.assertTrue(any(module in line for module in ("child_process", "path", "fs")))
        for forbidden in (".meta/scripts", "kb-guard", "host_guard"):
            self.assertNotIn(forbidden, plugin)
        pitch = read_repo_file("assets/pitch/presentation.html")
        self.assertEqual(pitch.count("<div"), pitch.count("</div>"))
        self.assert_contains_all(pitch, ["冻结基线", "独立验收", "恢复只读当前阶段", "可执行事实源优先"])
