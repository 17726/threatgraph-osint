"""Generate the data artifact manifest and README tables."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.artifact_naming import (
    canonical_doc_ids,
    validate_candidate_audit_filename,
    validate_evaluation_artifact_filename,
    validate_extraction_artifact_filename,
    validate_golden_artifact_filename,
)


CANDIDATE_AUDIT_SCHEMA_PATH = REPO_ROOT / "docs/schemas/candidate-audit.schema.json"


MANIFEST_VERSION = "1.0"
EXTRACTION_PREFIX = "extract-"
CANDIDATE_SUFFIX = "-candidate-audit.json"
LEGACY_CANDIDATE_AUDIT_NAME = "candidate-audit.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_candidate_audit_schema(payload: dict[str, Any]) -> None:
    schema = _load_json(CANDIDATE_AUDIT_SCHEMA_PATH)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise ValueError(f"candidate-audit schema 校验失败: {detail}")


def _status(path: str, previous: dict[str, Any]) -> dict[str, Any]:
    old = previous.get(path, {})
    return {
        "artifact_status": old.get(
            "artifact_status",
            "legacy" if "extract-v1" in path or "evaluation_result." in path else "current",
        ),
        **({"migration_note": old["migration_note"]} if "migration_note" in old else {}),
    }


def _previous_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    manifest = _load_json(path)
    records: dict[str, dict[str, Any]] = {}
    for group in ("goldens", "extractions", "evaluations"):
        for item in manifest.get(group, []):
            if "path" in item:
                records[item["path"]] = item
    return records


def _goldens(data_root: Path, previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for path in sorted((data_root / "golden").glob("*.json")):
        payload = _load_json(path)
        relative = path.relative_to(data_root.parent).as_posix()
        validate_golden_artifact_filename(relative, payload, allow_legacy=True)
        doc_ids = canonical_doc_ids(payload.get("doc_ids"))
        record = {
            "path": relative,
            "language": payload.get("language", ""),
            "doc_ids": doc_ids,
            "doc_id": "+".join(doc_ids),
            "schema_version": payload.get("schema_version", ""),
            "golden_version": payload.get("golden_version", ""),
            "content_sha256": _sha256(path),
            **_status(relative, previous),
        }
        records.append(record)
    return sorted(
        records,
        key=lambda item: (
            item["schema_version"], item["golden_version"], item["doc_id"],
            item["artifact_status"], item["path"],
        ),
    )


def _extractions(data_root: Path, previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    directory = data_root / "extracted"
    records = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(CANDIDATE_SUFFIX) or path.name == LEGACY_CANDIDATE_AUDIT_NAME:
            continue
        payload = _load_json(path)
        relative = path.relative_to(data_root.parent).as_posix()
        validate_extraction_artifact_filename(relative, payload, allow_legacy=True)
        run_id = payload.get("run_id", "")
        audit_path = directory / f"{run_id}{CANDIDATE_SUFFIX}"
        if not audit_path.is_file():
            legacy_audit_path = directory / LEGACY_CANDIDATE_AUDIT_NAME
            if legacy_audit_path.is_file():
                legacy_audit = _load_json(legacy_audit_path)
                if legacy_audit.get("run_id") == run_id:
                    audit_path = legacy_audit_path
        record = {
            "path": relative,
            "run_id": run_id,
            "doc_id": payload.get("doc_id", ""),
            "model_name": payload.get("model_name", ""),
            "prompt_version": payload.get("prompt_version", ""),
            "schema_version": payload.get("schema_version", ""),
            "generated_at": payload.get("generated_at", ""),
            "content_sha256": _sha256(path),
            **_status(relative, previous),
        }
        if audit_path.is_file():
            audit_payload = _load_json(audit_path)
            _validate_candidate_audit_schema(audit_payload)
            validate_candidate_audit_filename(
                audit_path.relative_to(data_root.parent).as_posix(),
                audit_payload,
                extraction_run_id=run_id,
                allow_legacy=True,
            )
            if audit_payload.get("doc_id") != payload.get("doc_id"):
                raise ValueError(
                    "candidate-audit doc_id 必须与 extraction result 的 doc_id 一致"
                )
            record["candidate_audit_path"] = audit_path.relative_to(data_root.parent).as_posix()
            record["candidate_audit_sha256"] = _sha256(audit_path)
        records.append(record)
    known_runs = {item["run_id"] for item in records}
    audit_paths = list(directory.glob(f"*{CANDIDATE_SUFFIX}"))
    legacy_audit_path = directory / LEGACY_CANDIDATE_AUDIT_NAME
    if legacy_audit_path.is_file():
        audit_paths.append(legacy_audit_path)
    for audit_path in sorted(audit_paths):
        audit = _load_json(audit_path)
        if audit.get("run_id") not in known_runs:
            raise ValueError(f"孤立 candidate-audit: {audit_path}")
    return sorted(
        records,
        key=lambda item: (
            item["schema_version"], item["prompt_version"], item["model_name"],
            item["doc_id"], item["generated_at"], item["artifact_status"], item["path"],
        ),
    )


def _evaluations(data_root: Path, previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for path in sorted((data_root / "evaluation").glob("*.json")):
        payload = _load_json(path)
        extraction = payload.get("extraction", {})
        golden = payload.get("golden", {})
        relative = path.relative_to(data_root.parent).as_posix()
        validate_evaluation_artifact_filename(relative, payload, allow_legacy=True)
        records.append({
            "path": relative,
            "doc_id": extraction.get("doc_id") or (golden.get("doc_ids") or [""])[0],
            "model_name": extraction.get("model_name", ""),
            "prompt_version": extraction.get("prompt_version", ""),
            "schema_version": extraction.get("schema_version", payload.get("schema_version", "")),
            "golden_version": golden.get("golden_version", ""),
            "evaluated_at": payload.get("evaluated_at", ""),
            "content_sha256": _sha256(path),
            **_status(relative, previous),
        })
    return sorted(
        records,
        key=lambda item: (
            item["schema_version"], item["prompt_version"], item["golden_version"],
            item["model_name"], item["doc_id"], item["evaluated_at"],
            item["artifact_status"], item["path"],
        ),
    )


def _link(data_root: Path, relative_path: str, label: str) -> str:
    href = relative_path.removeprefix("data/")
    return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'


def _rowspan_cells(rows: list[list[str]]) -> list[list[tuple[str, int] | None]]:
    result: list[list[tuple[str, int] | None]] = [[None] * len(row) for row in rows]
    for column in range(len(rows[0]) if rows else 0):
        index = 0
        while index < len(rows):
            end = index + 1
            while end < len(rows) and rows[end][column] == rows[index][column]:
                end += 1
            result[index][column] = (rows[index][column], end - index)
            index += 1
            while index < end:
                result[index][column] = None
                index += 1
    return result


def _table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    merged = _rowspan_cells(rows)
    lines = [f"## {title}", "", "<table>", "  <thead>", "    <tr>"]
    lines.extend(f"      <th>{html.escape(header)}</th>" for header in headers)
    lines.extend(["    </tr>", "  </thead>", "  <tbody>"])
    for row in merged:
        lines.append("    <tr>")
        for cell in row:
            if cell is not None:
                value, span = cell
                attribute = f' rowspan="{span}"' if span > 1 else ""
                lines.append(f"      <td{attribute}>{value}</td>")
        lines.append("    </tr>")
    lines.extend(["  </tbody>", "</table>", ""])
    return "\n".join(lines)


def _readme(data_root: Path, manifest: dict[str, Any]) -> str:
    golden_rows = [[
        html.escape(item["language"]), html.escape(item["doc_id"]),
        html.escape(item["schema_version"]), html.escape(item["golden_version"]),
        html.escape(item["artifact_status"]), _link(data_root, item["path"], "golden"),
    ] for item in manifest["goldens"]]
    extraction_rows = []
    for item in manifest["extractions"]:
        files = [_link(data_root, item["path"], "extract")]
        if item.get("candidate_audit_path"):
            files.append(_link(data_root, item["candidate_audit_path"], "candidate-audit"))
        extraction_rows.append([
            html.escape(item["doc_id"]), html.escape(item["schema_version"]),
            html.escape(item["prompt_version"]), html.escape(item["model_name"]),
            html.escape(item["generated_at"]), html.escape(item["artifact_status"]),
            "<br>".join(files),
        ])
    evaluation_rows = [[
        html.escape(item["doc_id"]), html.escape(item["schema_version"]),
        html.escape(item["prompt_version"]), html.escape(item["golden_version"]),
        html.escape(item["model_name"]), html.escape(item["evaluated_at"]),
        html.escape(item["artifact_status"]), _link(data_root, item["path"], "evaluation"),
    ] for item in manifest["evaluations"]]
    return "# 数据工件 Data Artifacts\n\n<!-- 自动生成文件，无需人工填写或编辑。 -->\n\n" + "\n".join([
        _table("黄金集 Golden", ["语言", "文档 ID", "Schema 版本", "Golden 版本", "状态", "文件"], golden_rows),
        _table("抽取结果 Extraction", ["文档 ID", "Schema 版本", "Prompt 版本", "模型", "运行时间", "状态", "文件"], extraction_rows),
        _table("评测结果 Evaluation", ["文档 ID", "Schema 版本", "Prompt 版本", "Golden 版本", "模型", "运行时间", "状态", "文件"], evaluation_rows),
    ])


def generate_artifacts(data_root: str | Path) -> tuple[dict[str, Any], str]:
    data_root = Path(data_root)
    manifest_path = data_root / "runs/index.json"
    previous = _previous_records(manifest_path)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_file": True,
        "generated_file_notice": "自动生成文件，无需人工填写或编辑。",
        "extractions": _extractions(data_root, previous),
        "goldens": _goldens(data_root, previous),
        "evaluations": _evaluations(data_root, previous),
    }
    return manifest, _readme(data_root, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    manifest, readme = generate_artifacts(args.data_root)
    (args.data_root / "runs").mkdir(parents=True, exist_ok=True)
    (args.data_root / "runs/index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.data_root / "README.md").write_text(readme, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
