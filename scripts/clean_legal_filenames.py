from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


PREFIX_PATTERN = re.compile(r"^(?:\d+[-_、．. ]*|[Xx][-_、．. ]*)+")


@dataclass(frozen=True)
class RenamePlan:
    """单个法规文件的重命名计划。"""

    source: Path
    target: Path


def clean_legal_filename(name: str) -> str:
    """清理法规文件名前缀中的临时序号或 X 标记。"""

    path = Path(name)
    cleaned_stem = PREFIX_PATTERN.sub("", path.stem).strip()
    cleaned_stem = re.sub(r"\s+", " ", cleaned_stem)
    return f"{cleaned_stem}{path.suffix}" if cleaned_stem else name


def build_rename_plans(directory: Path) -> list[RenamePlan]:
    """扫描目录，生成需要改名的法规文件计划。"""

    plans: list[RenamePlan] = []
    used_targets = {path.name for path in directory.iterdir() if path.is_file()}
    for source in sorted(path for path in directory.iterdir() if path.is_file()):
        cleaned_name = clean_legal_filename(source.name)
        if cleaned_name == source.name:
            continue
        target_name = _deduplicate_name(cleaned_name, used_targets, current_name=source.name)
        used_targets.add(target_name)
        plans.append(RenamePlan(source=source, target=source.with_name(target_name)))
    return plans


def apply_rename_plans(plans: list[RenamePlan]) -> None:
    """按计划执行重命名。"""

    for plan in plans:
        plan.source.rename(plan.target)


def _deduplicate_name(cleaned_name: str, used_targets: set[str], current_name: str) -> str:
    """目标文件名已存在时自动追加编号，避免覆盖文件。"""

    if cleaned_name not in used_targets or cleaned_name == current_name:
        return cleaned_name
    path = Path(cleaned_name)
    index = 2
    while True:
        candidate = f"{path.stem}_{index}{path.suffix}"
        if candidate not in used_targets:
            return candidate
        index += 1


def main() -> None:
    """命令行入口：默认只预览，传入 --apply 才真正重命名文件。"""

    parser = argparse.ArgumentParser(description="清理法规文件名前缀中的数字序号或 X 标记")
    parser.add_argument("--path", default="legalDocx", help="法规文件目录，默认 legalDocx")
    parser.add_argument("--apply", action="store_true", help="真正执行重命名；不加时只预览")
    args = parser.parse_args()

    directory = Path(args.path)
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parent.parent / directory
    if not directory.exists() or not directory.is_dir():
        raise SystemExit(f"目录不存在：{directory}")

    plans = build_rename_plans(directory)
    if not plans:
        print("没有需要清理的文件名。")
        return

    print(f"发现 {len(plans)} 个需要清理的文件名：")
    for plan in plans:
        print(f"- {plan.source.name} -> {plan.target.name}")

    if not args.apply:
        print("\n当前只是预览，没有修改文件。确认无误后追加 --apply 执行。")
        return

    apply_rename_plans(plans)
    print(f"\n已完成重命名：{len(plans)} 个文件。")


if __name__ == "__main__":
    main()
