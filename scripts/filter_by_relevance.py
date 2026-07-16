"""
基于统一 LLM 配置对 data/cleaned 下的 JSON 文档进行语义相关性过滤
和末尾无关内容清洗，输出到 data/cleaned_filtered。

功能：
1. 相关性判断 — 判断文档 clean_text 是否与目标 APT 组织高度相关
2. 文本清洗   — 删除末尾成块无关内容（订阅提示、版权声明、导航等）
3. 安全检查   — 验证清洗后文本是原文的子序列（只删不改）
4. 重新编号   — 过滤后按序重新分配 doc_id 和文件名

特性：
- 断点续传（默认开启，--no-resume 禁用）
- 抽样验证（--sample N，只处理前 N 个文件验证效果）
- 失败重试（默认 3 次，指数退避）
- 超长文本跳过保护（> 20000 字符）

用法：
    # 设置 API 密钥
    set LLM_MODEL=your-model
    set LLM_BASE_URL=https://your-provider.example/v1/chat/completions
    set LLM_API_KEY=sk-xxx

    # 抽样验证：先跑 3 个文件看看效果（花几分钱）
    python scripts/filter_by_relevance.py --sample 3

    # 确认无误后全量运行（会自动跳过已处理的 3 个）
    python scripts/filter_by_relevance.py

    # 仅处理单个文件夹
    python scripts/filter_by_relevance.py --folder apt28

    # 清除断点从头开始
    python scripts/filter_by_relevance.py --no-resume
"""

import argparse
import hashlib
import json
import os
import tempfile
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 配置 — 模型、接口地址和 API 密钥均通过环境变量设置
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # 秒
MAX_TEXT_LENGTH = 80000  # 超过此长度的 clean_text 跳过

# ---------------------------------------------------------------------------
# 目标组织描述
# ---------------------------------------------------------------------------
GROUP_INFO = {
    "apt28": {
        "name": "APT28",
        "description": (
            "APT28，又称 Fancy Bear、Sofacy Group、Pawn Storm、Sednit、STRONTIUM、Tsar Team，"
            "是一个与俄罗斯军方情报机构（GRU）相关的 APT 组织。"
            "主要活动：网络间谍、政治目标定向攻击、北约及欧洲政府机构渗透。"
        ),
    },
    "kimsuky": {
        "name": "Kimsuky",
        "description": (
            "Kimsuky，又称 Thallium、Velvet Chollima、Black Banshee，"
            "是一个与朝鲜侦察总局相关的 APT 组织。"
            "主要活动：情报收集、针对韩国政府/军事/智库/核能机构的定向攻击、社会工程学。"
        ),
    },
    "lazarus": {
        "name": "Lazarus Group",
        "description": (
            "Lazarus Group，又称 HIDDEN COBRA、Zinc、Diamond Sleet，"
            "下属 BlueNoroff（金融）、Andariel（破坏），"
            "是一个与朝鲜侦察总局相关的 APT 组织。"
            "主要活动：加密货币窃取、SWIFT 银行攻击、网络间谍、破坏性攻击。"
        ),
    },
}

# ---------------------------------------------------------------------------
# 提示词模板
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是一个网络安全情报文档分析助手。你的任务是对给定的文档完成两项工作，并严格以 JSON 格式返回结果。

## 目标组织
{target_name}
{target_description}

## 任务一：相关性判断
判断文档正文是否与 {target_name} 组织**高度相关**。

相关标准（满足任一即可）：
- 文档以 {target_name}（或其别名）为主要分析对象
- 文档实质性地讨论该组织的攻击活动、工具/技术、具体事件、IOC 指标、组织结构、成员关联和资金流向等部分或全部内容
- 文档深入分析该组织的 TTP（战术、技术、流程）、归因或威胁情报

不相关标准：
- 仅作为背景一笔带过，顺便提及但不以该组织为主要内容
- 完全不涉及该组织

**严格模式**：当无法明确判断是否相关时，判定为**不相关**。

## 任务二：文本清洗（仅当 is_relevant=true 时执行）
删除文档**末尾**的无关内容块。这些块通常特征明显且连续出现：

典型的末尾无关块：
- "Subscribe to our weekly e-mails"、"订阅我们的……" 等订阅提示区域
- "© 2026 AO Kaspersky Lab. All Rights Reserved." 等版权声明
- "Solutions for: Home Products Small Business…" 等产品导航菜单
- "相关文章推荐"、"最新发布"、"Latest Posts"、"From the same authors" 等内容推荐列表
- 社交媒体分享按钮文本、"Leave a Reply" 评论区入口
- 页面 footer 导航、重复的站点地图链接文字
- "参考链接"、"参考资料"后面与主题无关的聚合器链接列表
- "IOCs"后面来自搜索引擎的无关链接堆砌
- **转载声明**："转载请注明来源"、"转载请保留出处"、"转载自……"等
- **来源标注**：末尾孤立的"来源：xxx"、"文章来源：xxx"、"Source: xxx"
- **原文链接**："原文地址：https://..."、"阅读原文"、"查看原文"、"Original article:"
- **广告/推广**：课程推广、产品广告、赞助内容、"扫码关注"、"添加微信"等
- "*参考来源："后面跟着的网站来源声明（如果后面已无实质内容）
- "（完）"或"END"之后出现的一切非正文内容

清洗规则（**极其重要，必须严格遵守**）：
- **末尾只要是与文章主体内容无关的一切文字，全部删除**，不要局限于上面列举的类别
- **只能删除末尾的无关块，严禁修改、润色、改写正文中的任何一个字**
- 正文内容——即使看起来有些冗余或格式不佳——**必须原样保留，一字不改**
- 如果你不确定某段文字是否属于无关内容，**保留它（不删除）**
- 如果没有需要删除的末尾无关内容，cleaned_text 必须与原始文本**完全一致**
- 从文本末尾开始向前检查，只删除连续的无关内容块；一旦遇到正文内容就立即停止

## 返回格式
严格返回以下 JSON 对象，**不要包含 markdown 代码块标记或任何解释文字**：
{{
  "is_relevant": true,
  "cleaned_text": "清洗后的完整正文（is_relevant=false 时此字段为空字符串）"
}}
"""

USER_MESSAGE = """目标组织：{target_name}（{target_description}）

以下是需要分析的文档正文：
---
{clean_text}
---"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def build_prompt(folder: str, clean_text: str) -> tuple[str, str]:
    """根据文件夹名和目标组织构建 system / user 消息。"""
    info = GROUP_INFO[folder]
    system = SYSTEM_PROMPT.format(
        target_name=info["name"],
        target_description=info["description"],
    )
    user = USER_MESSAGE.format(
        target_name=info["name"],
        target_description=info["description"],
        clean_text=clean_text,
    )
    return system, user


def require_llm_config() -> tuple[str, str, str]:
    """读取并校验统一 LLM 配置，返回模型、接口地址和密钥。"""
    missing = [
        name
        for name in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError(f"未设置必需的 LLM 配置: {', '.join(missing)}")
    api_base = os.environ["LLM_BASE_URL"].strip().rstrip("/")
    if api_base.endswith("/chat/completions"):
        normalized_url = api_base
    elif api_base.endswith("/v1"):
        normalized_url = f"{api_base}/chat/completions"
    else:
        normalized_url = f"{api_base}/chat/completions"
    return (
        os.environ["LLM_MODEL"].strip(),
        normalized_url,
        os.environ["LLM_API_KEY"].strip(),
    )


def call_api(system: str, user: str) -> dict:
    """调用统一 OpenAI-compatible API，返回解析后的 JSON dict。"""
    model, api_base, api_key = require_llm_config()

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 16384,
    }, ensure_ascii=False).encode("utf-8")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                api_base,
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            content = body["choices"][0]["message"]["content"]
            return _parse_json_response(content)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            last_error = f"HTTP {e.code}: {err_body}"
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            last_error = f"响应解析失败: {e}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY_BASE ** attempt
            print(f"    ⚠ 第 {attempt} 次失败，{delay}s 后重试… "
                  f"（{last_error[:80]}）")
            time.sleep(delay)

    raise RuntimeError(f"API 调用失败（已重试 {MAX_RETRIES} 次）: {last_error}")


def _parse_json_response(content: str) -> dict:
    """从模型回复中提取 JSON 对象。"""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n", 1)
        if len(lines) > 1:
            content = lines[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    return json.loads(content)


def is_subsequence(original: str, cleaned: str) -> bool:
    """检查 cleaned 是否是 original 的子序列（只删不改）。"""
    it = iter(original)
    return all(ch in it for ch in cleaned)


def validate_cleaning(original: str, cleaned: str) -> Optional[str]:
    """验证清洗结果。返回 None 表示通过，否则返回警告信息。"""
    if not cleaned:
        return "cleaned_text 为空"
    if cleaned == original:
        return None

    if not is_subsequence(original, cleaned):
        it = iter(original)
        for i, ch in enumerate(cleaned):
            try:
                while next(it) != ch:
                    pass
            except StopIteration:
                snippet = cleaned[max(0, i - 20):i + 30]
                return (f"位置 ~{i} 不匹配: cleaned 中含原文没有的片段 "
                        f"\"…{snippet}…\"")
        return "子序列检查失败"
    return None


def compute_sha256(text: str) -> str:
    """计算文本的 SHA256 哈希。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_checkpoint(checkpoint_path: Path) -> dict:
    """加载断点文件。"""
    if checkpoint_path.exists():
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": {}, "warnings": []}


def save_checkpoint(checkpoint_path: Path, checkpoint: dict):
    """保存断点文件。"""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def write_progress(current: int, total: int, target: str) -> None:
    progress_path = os.environ.get("CRAWLER_PROGRESS_FILE")
    if not progress_path:
        return
    path = Path(progress_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "progress": {
            "phase": "validating",
            "current": current,
            "total": total,
            "target": target.upper(),
            "source": None,
            "message": "正在验证",
        }
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def process_folder(
    input_dir: Path, output_dir: Path, folder: str, sample: int = 0
) -> dict:
    """处理单个文件夹。sample>0 时只处理前 N 个待处理文件。返回统计 dict。"""
    output_subdir = output_dir / folder
    output_subdir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = output_dir / f".checkpoint_{folder}.json"
    checkpoint = load_checkpoint(checkpoint_path)
    processed_set = set(checkpoint["processed"].keys())

    json_files = sorted(input_dir.glob("*.json"))
    pending_files = [f for f in json_files if f.stem not in processed_set]
    write_progress(len(processed_set), len(json_files), folder)

    if not pending_files:
        print(f"  所有 {len(json_files)} 个文件已处理完毕，跳过")
        return _summarize(checkpoint, json_files)

    if sample > 0 and len(pending_files) > sample:
        print(f"  共 {len(json_files)} 个，已处理 {len(processed_set)}，"
              f"本次抽样处理前 {sample} 个")
        pending_files = pending_files[:sample]
    else:
        print(f"  共 {len(json_files)} 个，已处理 {len(processed_set)}，"
              f"待处理 {len(pending_files)}")

    for i, fpath in enumerate(pending_files, start=1):
        doc_id = fpath.stem
        cur = len(processed_set) + i
        total = len(json_files)
        write_progress(cur, total, folder)
        pbar = f"[{cur}/{total}]"

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"    {pbar} ⚠ [{doc_id}] 读取失败: {e}")
            checkpoint["processed"][doc_id] = "error"
            save_checkpoint(checkpoint_path, checkpoint)
            continue

        clean_text = data.get("clean_text", "") or ""

        if not clean_text.strip():
            print(f"    {pbar} ✕ [{doc_id}] clean_text 为空 → 丢弃")
            checkpoint["processed"][doc_id] = "discarded_empty"
            save_checkpoint(checkpoint_path, checkpoint)
            continue

        if len(clean_text) > MAX_TEXT_LENGTH:
            print(f"    {pbar} ⚠ [{doc_id}] 文本过长 ({len(clean_text)} 字符) → 跳过")
            checkpoint["processed"][doc_id] = "error_too_long"
            save_checkpoint(checkpoint_path, checkpoint)
            continue

        try:
            system, user = build_prompt(folder, clean_text)
            result = call_api(system, user)
        except Exception as e:
            print(f"    {pbar} ✗ [{doc_id}] API 失败: {e}")
            checkpoint["processed"][doc_id] = "error_api"
            save_checkpoint(checkpoint_path, checkpoint)
            continue

        is_relevant = result.get("is_relevant", False)
        new_text = result.get("cleaned_text", "")

        if not is_relevant:
            print(f"    {pbar} ✕ [{doc_id}] 不相关 → 丢弃")
            checkpoint["processed"][doc_id] = "discarded_irrelevant"
            save_checkpoint(checkpoint_path, checkpoint)
            continue

        # --- 相关文档：验证清洗结果 ---
        warning = validate_cleaning(clean_text, new_text)
        chars_removed = 0

        if warning:
            print(f"    {pbar} ⚠ [{doc_id}] 清洗验证失败: {warning}")
            print(f"         回退到原始文本，请人工复核")
            checkpoint["warnings"].append({"doc_id": doc_id, "warning": warning})
            new_text = clean_text
        elif new_text == clean_text:
            print(f"    {pbar} ✓ [{doc_id}] 相关，末尾无需清洗")
        else:
            chars_removed = len(clean_text) - len(new_text)
            print(f"    {pbar} ✓ [{doc_id}] 相关，已清洗（-{chars_removed} 字符）")

        # 更新字段
        data["clean_text"] = new_text
        data["content_hash"] = compute_sha256(new_text)

        # 追加处理记录到 metadata
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["relevance_filter"] = {
            "model": require_llm_config()[0],
            "result": "kept",
            "chars_removed": chars_removed,
            "validation_warning": warning,
        }

        temp_file = output_subdir / f"{doc_id}.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        checkpoint["processed"][doc_id] = "kept"
        save_checkpoint(checkpoint_path, checkpoint)

    return _summarize(checkpoint, json_files)


def _summarize(checkpoint: dict, json_files: list) -> dict:
    """从断点文件汇总统计。"""
    kept = sum(1 for v in checkpoint["processed"].values() if v == "kept")
    discarded = sum(1 for v in checkpoint["processed"].values()
                    if v.startswith("discarded"))
    errors = sum(1 for v in checkpoint["processed"].values()
                 if v.startswith("error"))
    return {
        "total": len(json_files),
        "kept": kept,
        "discarded": discarded,
        "errors": errors,
    }


def renumber_folder(output_dir: Path, folder: str):
    """重新编号：doc_id → {folder}_001, ..."""
    output_subdir = output_dir / folder
    if not output_subdir.exists():
        return

    json_files = sorted(output_subdir.glob("*.json"))
    json_files.sort(key=lambda p: p.stem)

    for idx, fpath in enumerate(json_files, start=1):
        new_doc_id = f"{folder}_{idx:03d}"

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        old_doc_id = data.get("doc_id", fpath.stem)
        data["doc_id"] = new_doc_id

        new_path = output_subdir / f"{new_doc_id}.json"
        with open(new_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if fpath != new_path and fpath.stem != new_doc_id:
            fpath.unlink()

        print(f"    {old_doc_id} → {new_doc_id}.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="基于统一 LLM 配置的文档相关性过滤与文本清洗"
    )
    parser.add_argument(
        "--sample", type=int, default=0, metavar="N",
        help="抽样验证：每个文件夹只处理前 N 个文件（默认 0 = 全量处理）"
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="禁用断点续传，清除进度从头开始"
    )
    parser.add_argument(
        "--folder", choices=["apt28", "kimsuky", "lazarus"],
        help="仅处理指定文件夹（不指定则处理全部三个）"
    )
    return parser


def main():
    args = build_parser().parse_args()
    model, _, _ = require_llm_config()

    project_root = Path(__file__).resolve().parent.parent
    data_root = Path(os.getenv("CRAWLER_DATA_ROOT", str(project_root / "data")))
    input_dir = data_root / "cleaned"
    output_dir = data_root / "cleaned_filtered"

    folders = [args.folder] if args.folder else ["apt28", "kimsuky", "lazarus"]

    if args.sample > 0:
        print("=" * 60)
        print(f"🔍 抽样验证 — 每个文件夹只处理前 {args.sample} 个文件")
        print("=" * 60)
    else:
        print("=" * 60)
        print("相关性过滤 & 文本清洗")
        print(f"模型: {model}")
        print(f"输入: {input_dir}")
        print(f"输出: {output_dir}")
        print("=" * 60)

    if args.no_resume:
        for folder in folders:
            cp = output_dir / f".checkpoint_{folder}.json"
            if cp.exists():
                cp.unlink()
                print(f"[{folder}] 已清除断点文件")

    grand_total = 0
    grand_kept = 0
    grand_discarded = 0
    grand_errors = 0

    for folder in folders:
        in_dir = input_dir / folder
        if not in_dir.is_dir():
            print(f"\n[{folder}] ⚠ 输入目录不存在，跳过")
            continue

        print(f"\n{'─' * 50}")
        print(f"[{folder}]")
        stats = process_folder(in_dir, output_dir, folder, sample=args.sample)

        if stats["kept"] > 0:
            print(f"\n[{folder}] 重新编号…")
            renumber_folder(output_dir, folder)

        print(f"\n[{folder}] 汇总: 保留 {stats['kept']} | "
              f"丢弃 {stats['discarded']} | 错误 {stats['errors']} "
              f"（共 {stats['total']}）")

        cp = output_dir / f".checkpoint_{folder}.json"
        if cp.exists():
            with open(cp, "r", encoding="utf-8") as f:
                ck = json.load(f)
            warnings = ck.get("warnings", [])
            if warnings:
                print(f"  ⚠ 清洗验证警告 {len(warnings)} 条，请人工复核：")
                for w in warnings:
                    print(f"    - {w['doc_id']}: {w['warning']}")

        grand_total += stats["total"]
        grand_kept += stats["kept"]
        grand_discarded += stats["discarded"]
        grand_errors += stats["errors"]

    print("\n" + "=" * 60)
    print(f"总计: {grand_total} 文件 → 保留 {grand_kept} | "
          f"丢弃 {grand_discarded} | 错误 {grand_errors}")
    print("=" * 60)

    if grand_errors > 0:
        print("\n⚠ 有文件处理出错。修复后重新运行脚本即可断点续传。")
    if args.sample > 0:
        print(f"\n💡 抽样验证完毕。确认无误后去掉 --sample 参数全量运行。")


if __name__ == "__main__":
    main()
