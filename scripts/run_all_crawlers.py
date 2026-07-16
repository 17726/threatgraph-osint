from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON_EXE = sys.executable

CRAWLER_SOURCES = {
    "crawler_v1": ("qianxin", "thehackernews", "unit42", "freebuf"),
    "crawler_supplementary": ("chainalysis", "trmlabs", "microsoft", "securelist"),
    "crawler_supplementary_v2": ("crowdstrike", "groupib", "ofac", "fbi"),
}
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


def normalize_sources(value: str) -> list[str]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested:
        raise ValueError("sources cannot be empty")
    if "all" in requested:
        if len(requested) != 1:
            raise ValueError("sources=all cannot be combined with individual sources")
        return [source for sources in CRAWLER_SOURCES.values() for source in sources]
    unknown = [source for source in requested if source not in SOURCE_OWNERS]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}")
    return list(dict.fromkeys(requested))


def group_sources(source_value: str) -> dict[str, list[str]]:
    selected = normalize_sources(source_value)
    grouped = {crawler: [] for crawler in CRAWLER_SOURCES}
    for source in selected:
        grouped[SOURCE_OWNERS[source]].append(source)
    return {crawler: sources for crawler, sources in grouped.items() if sources}


def target_folder(keyword: str) -> str:
    normalized = keyword.strip().lower()
    return TARGET_GROUPS.get(normalized, normalized.replace(" ", "_"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一运行 ThreatGraph-OSINT 爬虫流水线")
    parser.add_argument("--keyword", required=True, help="目标组织或搜索关键词")
    parser.add_argument("--limit", required=True, type=positive_limit, help="每个来源的最大文章数")
    parser.add_argument("--filter", action="store_true", help="启用相关性过滤和末尾清洗")
    parser.add_argument("--sources", required=True, help="逗号分隔来源名或 all")
    return parser


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    grouped = group_sources(args.sources)
    commands: list[list[str]] = []
    for crawler, sources in grouped.items():
        commands.append(
            [
                PYTHON_EXE,
                str(CRAWLER_PATHS[crawler]),
                "--keyword",
                args.keyword,
                "--limit",
                str(args.limit),
                "--source",
                ",".join(sources),
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

    input_dir = PROJECT_ROOT / "data" / ("cleaned_filtered" if args.filter else "cleaned")
    commands.append(
        [
            PYTHON_EXE,
            str(SCRIPTS_DIR / "promote_cleaned_documents.py"),
            "--input",
            str(input_dir),
            "--output",
            str(PROJECT_ROOT / "data" / "documents"),
            "--target-group",
            target_folder(args.keyword),
        ]
    )
    return commands


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        commands = build_commands(args)
    except ValueError as exc:
        parser.error(str(exc))

    for index, command in enumerate(commands, start=1):
        print(f"[{index}/{len(commands)}] {' '.join(command)}")
        completed = subprocess.run(command, check=False, cwd=PROJECT_ROOT)
        if completed.returncode:
            print(f"命令失败，返回码：{completed.returncode}", file=sys.stderr)
            return completed.returncode

    print("爬虫流水线执行完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
