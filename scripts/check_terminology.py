"""Check user-facing terminology drift.

This guard is intentionally scoped to user-visible Network Editor surfaces and
supporting docs. It does not rename API fields, issue codes, test ids, or DB
columns such as feature_key and covered_leaf_state_ids.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = [
    ROOT / "frontend" / "src" / "views" / "DataManagement",
    ROOT / "docs" / "network-editor-user-guide.md",
    ROOT / "docs" / "network-editor-acceptance-matrix.md",
]

TEXT_SUFFIXES = {".js", ".ts", ".vue", ".md", ".json"}


@dataclass(frozen=True)
class Rule:
    term: str
    canonical: str
    note: str


RULES = [
    Rule("旧版可执行活动", "旧执行活动", "历史活动层级名应对齐 ANCHOR.md V0.3"),
    Rule("可执行活动", "原子活动", "仅在说明求解器执行时把“可执行”作为形容词使用"),
    Rule("叶子", "原子状态", "用户可见状态层级统一称原子状态；树形 UI 可改为条目/底层状态"),
    Rule("特征键", "状态维度（feature_key）", "非技术表头和说明应使用状态维度"),
]

TECHNICAL_FEATURE_KEY_ALLOWLIST = {
    ROOT / "frontend" / "src" / "views" / "DataManagement" / "FeatureDefPage.vue",
    ROOT / "frontend" / "src" / "views" / "DataManagement" / "RulePage.vue",
    ROOT / "frontend" / "src" / "views" / "DataManagement" / "StateHierarchyPage.vue",
}


def iter_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = target if target.is_absolute() else ROOT / target
        if path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES
            )
        elif path.is_file():
            files.append(path)
    return sorted(set(files))


def is_allowed(path: Path, rule: Rule, line: str) -> bool:
    if rule.term == "特征键" and path.resolve() in TECHNICAL_FEATURE_KEY_ALLOWLIST:
        return True
    return False


def check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig", errors="replace")

    violations: list[str] = []
    rel_path = path.relative_to(ROOT)
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule in RULES:
            if rule.term not in line:
                continue
            if is_allowed(path, rule, line):
                continue
            clean_line = line.strip()
            violations.append(
                f"{rel_path}:{line_no}: found '{rule.term}', use '{rule.canonical}'. "
                f"{rule.note}. line: {clean_line}"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check user-facing terminology drift.")
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional files or directories to scan. Defaults to Network Editor user-visible surfaces.",
    )
    args = parser.parse_args()

    targets = [Path(item) for item in args.targets] if args.targets else DEFAULT_TARGETS
    files = iter_files(targets)
    violations: list[str] = []
    for path in files:
        violations.extend(check_file(path))

    if violations:
        print("Terminology drift found:")
        for item in violations:
            print(f"- {item}")
        return 1

    print(f"Terminology check passed ({len(files)} files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
