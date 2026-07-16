from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.crawler_proxy import configure_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON_EXE = sys.executable

CRAWLER_SOURCES = {
    "crawler_v1": ("qianxin", "thehackernews", "unit42", "freebuf"),
    "crawler_supplementary": ("chainalysis", "trmlabs", "microsoft", "securelist"),
    "crawler_supplementary_v2": ("crowdstrike", "groupib", "ofac", "fbi"),
}
CRAWLER_WIDTHS = {crawler: len(sources) for crawler, sources in CRAWLER_SOURCES.items()}
TOTAL_SOURCE_BITS = sum(CRAWLER_WIDTHS.values())
MAX_SOURCE_MASK = (1 << TOTAL_SOURCE_BITS) - 1
SOURCE_OWNERS = {
    source: crawler
    for crawler, sources in CRAWLER_SOURCES.items()
    for source in sources
}
CRAWLER_PATHS = {
    "crawler_v1": SCRIPTS_DIR / "crawler_v1.py",
    "crawler_supplementary": SCRIPTS_DIR / "crawler_supplementary.py",
    "crawler_supplementary_v2": SCRIPTS_DIR / "crawler_supplementary_v2.py",
}
TARGET_GROUPS = {
    "apt28": "apt28",
    "fancy bear": "apt28",
    "sofacy": "apt28",
    "kimsuky": "kimsuky",
    "apt43": "kimsuky",
    "velvet chollima": "kimsuky",
    "lazarus": "lazarus",
    "lazarus group": "lazarus",
    "hidden cobra": "lazarus",
    "apt38": "lazarus",
}


def positive_limit(value: str) -> int:
    limit = int(value)
    if limit <= 0:
        raise argparse.ArgumentTypeError("limit must be greater than zero")
    return limit


def positive_start_number(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("start-number must be greater than zero")
    return number


def parse_sources_mask(value: str) -> int:
    try:
        sources = int(value, 10)
    except ValueError as exc:
        raise ValueError("sources must be a decimal integer") from exc
    if sources <= 0:
        raise ValueError("sources must be greater than zero")
    if sources > MAX_SOURCE_MASK:
        raise ValueError(f"sources exceeds the {TOTAL_SOURCE_BITS}-bit layout")
    return sources


def group_source_masks(sources: int) -> dict[str, int]:
    if sources <= 0:
        raise ValueError("sources must be greater than zero")
    if sources > MAX_SOURCE_MASK:
        raise ValueError(f"sources exceeds the {TOTAL_SOURCE_BITS}-bit layout")

    remaining = sources
    grouped: dict[str, int] = {}
    for crawler, width in CRAWLER_WIDTHS.items():
        local_mask = remaining & ((1 << width) - 1)
        remaining >>= width
        if local_mask:
            grouped[crawler] = local_mask
    if remaining:
        raise ValueError("sources contains undefined high bits")
    return grouped


def target_folder(keyword: str) -> str:
    normalized = keyword.strip().lower()
    return TARGET_GROUPS.get(normalized, normalized.replace(" ", "_"))


def data_root() -> Path:
    return Path(os.getenv("CRAWLER_DATA_ROOT", str(PROJECT_ROOT / "data")))


def merge_cleaned_documents(source_root: Path, target_root: Path) -> int:
    """Merge isolated crawler output without allowing legacy IDs to collide."""
    merged = 0
    target_root.mkdir(parents=True, exist_ok=True)
    for crawler in CRAWLER_SOURCES:
        source_dir = source_root / crawler / "cleaned"
        if not source_dir.exists():
            continue
        for path in sorted(source_dir.rglob("*.json")):
            relative = path.relative_to(source_dir)
            target_dir = target_root / relative.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{crawler}__{path.name}"
            shutil.copy2(path, target_path)
            merged += 1
    return merged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一运行 ThreatGraph-OSINT 爬虫流水线")
    parser.add_argument("--keyword", required=True, help="目标组织或搜索关键词")
    parser.add_argument("--limit", required=True, type=positive_limit, help="每个来源的最大文章数")
    parser.add_argument("--filter", action="store_true", help="启用相关性过滤和末尾清洗")
    parser.add_argument("--sources", required=True, type=parse_sources_mask, help="全局来源整数掩码")
    parser.add_argument("--start-number", type=positive_start_number, default=1)
    return parser


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    grouped = group_source_masks(args.sources)
    commands: list[list[str]] = []
    for crawler, local_mask in grouped.items():
        commands.append(
            [
                PYTHON_EXE,
                str(CRAWLER_PATHS[crawler]),
                "--keyword",
                args.keyword,
                "--limit",
                str(args.limit),
                "--sources",
                str(local_mask),
            ]
        )

    if args.filter:
        commands.append(
            [
                PYTHON_EXE,
                str(SCRIPTS_DIR / "filter_by_relevance.py"),
                "--folder",
                target_folder(args.keyword),
            ]
        )

    input_dir = data_root() / ("cleaned_filtered" if args.filter else "cleaned")
    commands.append(
        [
            PYTHON_EXE,
            str(SCRIPTS_DIR / "promote_cleaned_documents.py"),
            "--input",
            str(input_dir),
            "--output",
            str(data_root() / "documents"),
            "--start-number",
            str(args.start_number),
        ]
    )
    return commands


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_environment()
    try:
        commands = build_commands(args)
    except ValueError as exc:
        parser.error(str(exc))

    failed = False
    crawler_count = len(group_source_masks(args.sources))
    root = data_root()
    for index, command in enumerate(commands[:crawler_count], start=1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}")
        crawler_name = Path(command[1]).stem
        crawler_root = root / crawler_name
        crawler_root.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "CRAWLER_DATA_ROOT": str(crawler_root)}
        completed = subprocess.run(
            command,
            check=False,
            cwd=PROJECT_ROOT,
            env=environment,
        )
        if completed.returncode:
            print(f"命令失败，返回码：{completed.returncode}", file=sys.stderr)
            failed = True

    if not failed:
        merged_root = root / "cleaned"
        if merged_root.exists():
            shutil.rmtree(merged_root)
        merge_cleaned_documents(root, merged_root)

    if failed:
        print("crawler 阶段失败，跳过过滤和 promote。", file=sys.stderr)
        print("爬虫流水线执行完成。")
        return 1

    for index, command in enumerate(commands[crawler_count:], start=crawler_count + 1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}")
        completed = subprocess.run(
            command,
            check=False,
            cwd=PROJECT_ROOT,
            env={**os.environ, "CRAWLER_DATA_ROOT": str(root)},
        )
        if completed.returncode:
            print(f"命令失败，返回码：{completed.returncode}", file=sys.stderr)
            failed = True
            if "filter_by_relevance.py" in command[1]:
                print("过滤失败，跳过 promote，避免将不完整输出导入。", file=sys.stderr)
                break

    print("爬虫流水线执行完成。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
