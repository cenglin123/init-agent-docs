from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK_NAMES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
LINK_PATHS = [ROOT / name for name in LINK_NAMES]
SOURCE = LINK_PATHS[0]


def same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except FileNotFoundError:
        return False


def link_key(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_dev, stat.st_ino


def describe() -> list[str]:
    rows = []
    for path in LINK_PATHS:
        key = link_key(path)
        if key is None:
            rows.append(f"{path.name}: missing")
            continue
        stat = path.stat()
        rows.append(f"{path.name}: dev={key[0]} inode={key[1]} nlink={stat.st_nlink}")
    return rows


def is_link_group_intact() -> bool:
    keys = [link_key(path) for path in LINK_PATHS]
    return all(key is not None for key in keys) and len(set(keys)) == 1


def command_check(args: argparse.Namespace) -> None:
    if args.verbose:
        print("\n".join(describe()))
    if not is_link_group_intact():
        raise SystemExit("AGENTS.md / CLAUDE.md / GEMINI.md hardlink group is broken")
    print("hardlink group ok")


def file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def repair_target(target: Path, force: bool) -> None:
    if same_file(SOURCE, target):
        return

    if target.exists() and file_text(target) != file_text(SOURCE) and not force:
        raise SystemExit(
            f"{target.name} content differs from AGENTS.md; rerun with --force only after review"
        )

    if target.exists():
        target.unlink()
    os.link(SOURCE, target)
    print(f"linked {target.name} -> {SOURCE.name}")


def command_repair(args: argparse.Namespace) -> None:
    if not SOURCE.is_file():
        raise SystemExit("AGENTS.md is missing; cannot repair hardlinks")

    for target in LINK_PATHS[1:]:
        repair_target(target, args.force)

    if not is_link_group_intact():
        print("\n".join(describe()), file=sys.stderr)
        raise SystemExit("repair failed")
    print("hardlink group ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or repair AGENTS.md / CLAUDE.md / GEMINI.md hardlinks."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Verify all three files are the same hardlink.")
    check.add_argument("--verbose", action="store_true")
    check.set_defaults(func=command_check)

    repair = sub.add_parser("repair", help="Recreate CLAUDE.md and GEMINI.md as hardlinks.")
    repair.add_argument(
        "--force",
        action="store_true",
        help="Overwrite differing CLAUDE.md/GEMINI.md content after manual review.",
    )
    repair.set_defaults(func=command_repair)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
