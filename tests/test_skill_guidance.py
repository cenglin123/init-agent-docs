"""Static regression checks for high-signal init-agent-docs guidance."""
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


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
                "copy 同步（默认）",
                "docs/STRUCTURE.md",
                "docs/CHANGELOG.md",
                ".agents/memory/MEMORY.md",
                "docs/problems/bugfix/",
                "scripts/maintain.py",
                "worktree_task.py",
                "Occam",
                "Bitter Lesson",
                "小型 / 中型 / 大型",
                "git fetch origin",
            ],
        )
        self.assertNotIn("100 行", pitch)
        self.assertNotIn("~100行", pitch)
        self.assertNotIn("CLAUDE.md / GEMINI.md (硬链接)", pitch)
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
                "python scripts/worktree_task.py create",
                "workflow-patterns.md",
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
