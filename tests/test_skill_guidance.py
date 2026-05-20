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
                "最终生成 AGENTS.md 前逐条过滤",
                "本 skill 创建的机制需要 Agent 记住",
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


if __name__ == "__main__":
    unittest.main()
