"""Run the source repository's R2 gate without auditing generated-project assets."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="include the candidate commit's staged score row")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("source_audit", root / "assets/scripts/audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    rows = audit._check_eval_baseline(staged=args.staged)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return int(any(row["status"] not in ("ok", "warn", "skip") for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
