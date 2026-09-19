"""Static regression checks for high-signal init-agent-docs guidance."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def project_repository_mode(text: str, mode: str) -> str:
    """Apply the template's explicit Git/no-Git blocks, then remove guidance comments."""
    lines: list[str] = []
    active_mode: str | None = None
    for line in text.splitlines():
        marker = line.strip()
        if marker == "<!-- Git profile only -->":
            if active_mode is not None:
                raise AssertionError("nested repository profile block")
            active_mode = "git"
            continue
        if marker == "<!-- no-Git profile only -->":
            if active_mode is not None:
                raise AssertionError("nested repository profile block")
            active_mode = "no-git"
            continue
        if marker == "<!-- /Git profile only -->":
            if active_mode != "git":
                raise AssertionError("unbalanced Git profile block")
            active_mode = None
            continue
        if marker == "<!-- /no-Git profile only -->":
            if active_mode != "no-git":
                raise AssertionError("unbalanced no-Git profile block")
            active_mode = None
            continue
        if active_mode is None or active_mode == mode:
            lines.append(line)
    if active_mode is not None:
        raise AssertionError(f"unclosed {active_mode} profile block")
    return re.sub(r"<!--.*?-->", "", "\n".join(lines), flags=re.DOTALL)


class SkillGuidanceTestCase(unittest.TestCase):
    def assert_contains_all(self, text: str, expected: list[str]) -> None:
        for item in expected:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_skill_mentions_source_priority_and_instruction_files(self) -> None:
        text = read_repo_file("SKILL.md")

        self.assert_contains_all(
            text,
            [
                "`README*`、根目录 manifest、workspace 配置、lockfile",
                "可执行事实源优先于 prose 文档",
                ".cursor/rules/**",
                ".github/copilot-instructions.md",
                "opencode.json",
                "信息归口冲突",
                "事实内容冲突",
                "最终目标项目文件不得残留 HTML 指导注释或 `[方括号]` 占位符",
            ],
        )

    def test_agents_template_keeps_core_mechanisms_but_filters_generic_rules(self) -> None:
        text = read_repo_file("assets/templates/zh/AGENTS.md.tpl")

        self.assert_contains_all(
            text,
            [
                "必须保持精简",
                "只放行为规则和信息指针",
                "候选项：只有目标仓库已有约束或用户确认时保留",
                "AGENTS.md 是唯一入口",
                "当前选定的控制器",
            ],
        )

    def test_eval_baseline_covers_absorbed_init_behaviors(self) -> None:
        text = read_repo_file("assets/references/eval-baseline.md")

        self.assert_contains_all(
            text,
            [
                "可执行事实源优先",
                "已有 instruction 文件整合",
                "README 写旧命令",
                "Small + no-Git",
                "Medium + Git",
                "静态合同",
                "合成树",
                "行为评估",
            ],
        )

    def test_maintain_pipeline_and_memory_retrieval_guidance(self) -> None:
        skill = read_repo_file("SKILL.md")
        self.assert_contains_all(
            skill,
            [
                "maintain.py",
                "任务前记忆检索",
                "memory-index:start",
                "scripts/maintain.py --memory-index",
                "手工维护 MEMORY.md 索引",
            ],
        )

        tpl = read_repo_file("assets/templates/zh/AGENTS.md.tpl")
        self.assert_contains_all(
            tpl,
            [
                "任务前记忆检索",
                "查经验系统",
                "检索动作必须发生",
                "Bugfix 沉淀",
                "python scripts/maintain.py",
            ],
        )

        memory_tpl = read_repo_file("assets/templates/zh/MEMORY.md.tpl")
        self.assert_contains_all(
            memory_tpl,
            [
                "<!-- memory-index:start -->",
                "<!-- memory-index:end -->",
                "禁止手工编辑标记段内容",
                "维护分工",
                "docs/problems/bugfix/",
            ],
        )

        bugfix_tpl = read_repo_file("assets/templates/zh/bugfix.md.tpl")
        self.assert_contains_all(
            bugfix_tpl,
            [
                "liveness",
                "last_confirmed",
                "confirmed_count",
                "verification",
                "怎么修复的",
            ],
        )

    def test_delivery_files_use_agents_memory_directory(self) -> None:
        delivery_files = [
            "SKILL.md",
            "README.md",
            "assets/scripts/maintain.py",
            "assets/scripts/audit.py",
            "assets/templates/zh/AGENTS.md.tpl",
            "assets/templates/zh/MEMORY.md.tpl",
            "assets/templates/zh/audit-checklist.md.tpl",
            "assets/templates/zh/bugfix.md.tpl",
            "assets/hooks/pre-commit-generic.sh",
            "assets/hooks/pre-commit-python.sh",
            "assets/hooks/pre-commit-node.sh",
            "assets/hooks/pre-commit-go.sh",
        ]
        for path in delivery_files:
            with self.subTest(path=path):
                text = read_repo_file(path)
                self.assertNotIn(".agent/", text)
                self.assertIn(".agents/memory", text)

    def test_pitch_deck_tracks_current_project_contract(self) -> None:
        pitch = read_repo_file("assets/pitch/presentation.html")

        self.assert_contains_all(
            pitch,
            [
                "200 行 / 400 词",
                "可执行事实源优先",
                "唯一入口",
                "docs/STRUCTURE.md",
                "docs/CHANGELOG.md",
                ".agents/memory/MEMORY.md",
                "docs/problems/bugfix/",
                "scripts/maintain.py",
                "worktree_task.py",
                "Occam",
                "Bitter Lesson",
                "小型 / 中型 / 大型",
                "Git / no-Git",
                "当前选定的控制器",
            ],
        )
        self.assertNotIn("100 行", pitch)
        self.assertNotIn("~100行", pitch)
        self.assertNotIn("CLAUDE.md / GEMINI.md (硬链接)", pitch)
        self.assertNotIn("agent_links", pitch)
        self.assertNotIn("绝对不记", pitch)

    def test_bitter_lesson_boundary_terms_present(self) -> None:
        skill = read_repo_file("SKILL.md")
        self.assert_contains_all(
            skill,
            [
                "封顶型先验",
                "防呆型机制",
                "逃生舱",
                "fail-closed",
                "fail-open",
            ],
        )

    def test_worktree_runtime_guidance_present(self) -> None:
        skill = read_repo_file("SKILL.md")
        self.assert_contains_all(
            skill,
            [
                "第 6.5 步",
                "worktree_task.py",
                "reference-transaction",
                "worktree-task.canonicalRef",
                "并行协作共享同一工作树",
            ],
        )

        tpl = read_repo_file("assets/templates/zh/AGENTS.md.tpl")
        self.assert_contains_all(
            tpl,
            [
                "多 Agent worktree 路由",
                "python scripts/worktree_task.py --help",
                "仅 Git profile",
            ],
        )

        patterns = read_repo_file("assets/references/workflow-patterns.md")
        self.assert_contains_all(
            patterns,
            [
                "worktree_task 四动作",
                "git-dir == common-dir",
                "head-drift",
                "partial-state",
            ],
        )

    def test_four_profile_contracts_and_birth_records_are_explicit(self) -> None:
        skill = read_repo_file("SKILL.md")
        for profile in ("Small + Git", "Small + no-Git", "Medium/Large + Git", "Medium/Large + no-Git"):
            self.assertIn(profile, skill)
        self.assertIn("docs/initialization.md", skill)
        self.assertIn("docs/plans/completed/initialization.md", skill)
        self.assertIn("repository_mode", skill)
        self.assertIn("size", skill)
        self.assertIn("不会自动执行 `git init`", skill)

    def test_small_no_git_contract_has_explicit_omissions(self) -> None:
        skill = read_repo_file("SKILL.md")
        marker = "#### Small + no-Git"
        self.assertIn(marker, skill)
        section = skill.split(marker, 1)[1].split("#### ", 1)[0]
        for term in ("docs/plans/", ".agents/memory/", "docs/overview.md", ".githooks/", "worktree"):
            self.assertIn(term, section)
        self.assertIn("不得生成", section)

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
        skill_text = read_repo_file("SKILL.md")
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

    def test_skill_preflight_and_hooks_respect_repository_mode(self) -> None:
        skill = read_repo_file("SKILL.md")
        preflight = skill.split("### 前置检查：", 1)[1].split("### 第 0 步：", 1)[0]
        self.assertNotIn("origin/main", preflight)
        self.assertIn("no-Git profile 不运行任何 Git 命令", preflight)
        self.assertIn("只有用户明确确认将 no-Git 目标转换为 Git 后", skill)
        self.assertIn("no-Git profile 跳过整个 hook 步骤", skill)

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


if __name__ == "__main__":
    unittest.main()
