#!/usr/bin/env python3
"""
集成爬虫调度脚本 - 自动适配路径
依次执行：
  1. crawler_v1.py        --keyword <keyword> --limit 2
  2. crawler_supplementary.py --source all --keyword <keyword> --limit 2
  3. crawler_supplementary_v2.py --source groupib --keyword <keyword> --limit 2
  4. crawler_supplementary_v2.py --source ofac --keyword <keyword> --limit 2

使用方法：
    python run_all_crawlers.py
    然后根据提示输入关键词（例如 APT28）
"""

import subprocess
import sys
from pathlib import Path

# ---------- 路径自动适配 ----------
# 获取当前脚本所在目录
current_dir = Path(__file__).resolve().parent

# 判断当前目录是否是项目根目录（即存在 scripts 子文件夹）
if (current_dir / "scripts").exists():
    PROJECT_ROOT = current_dir
    SCRIPTS_DIR = current_dir / "scripts"
else:
    # 否则假设当前已经在 scripts 目录下
    PROJECT_ROOT = current_dir.parent
    SCRIPTS_DIR = current_dir

# 若仍未找到 scripts，报错提示
if not SCRIPTS_DIR.exists():
    print("错误：找不到 scripts 目录，请将脚本放在项目根目录或 scripts/ 目录下。")
    sys.exit(1)

# 使用当前 Python 解释器路径（避免多版本问题）
PYTHON_EXE = sys.executable

# 定义要执行的命令
COMMANDS = [
    [PYTHON_EXE, str(SCRIPTS_DIR / "crawler_v1.py"), "--keyword", "{keyword}", "--limit", "2"],
    #[PYTHON_EXE, str(SCRIPTS_DIR / "crawler_supplementary.py"), "--source", "all", "--keyword", "{keyword}", "--limit", "2"],
    #[PYTHON_EXE, str(SCRIPTS_DIR / "crawler_supplementary_v2.py"), "--source", "groupib", "--keyword", "{keyword}", "--limit", "2"],
    #[PYTHON_EXE, str(SCRIPTS_DIR / "crawler_supplementary_v2.py"), "--source", "ofac", "--keyword", "{keyword}", "--limit", "2"],
]

def main():
    # 提示输入关键词
    keyword = input("请输入要爬取的关键词（例如 APT28, Kimsuky, Lazarus）：").strip()
    if not keyword:
        print("错误：关键词不能为空！")
        sys.exit(1)

    print(f"\n准备开始爬取，关键词：{keyword}")
    print("=" * 60)

    # 依次执行
    for idx, cmd_template in enumerate(COMMANDS, start=1):
        cmd = [arg.format(keyword=keyword) for arg in cmd_template]
        print(f"\n[步骤 {idx}/{len(COMMANDS)}] 执行命令：{' '.join(cmd)}")
        print("-" * 60)

        try:
            subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
            print(f"[步骤 {idx}] 完成")
        except subprocess.CalledProcessError as e:
            print(f"[步骤 {idx}] 执行失败，返回码：{e.returncode}", file=sys.stderr)
            print("终止后续爬虫执行。")
            sys.exit(e.returncode)

    print("\n" + "=" * 60)
    print("所有爬虫执行完毕！输出文件位于 data/documents/<关键词>/ 目录下。")

if __name__ == "__main__":
    main()
