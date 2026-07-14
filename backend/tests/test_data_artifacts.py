import json
from pathlib import Path

import pytest

from scripts.generate_data_artifacts import generate_artifacts


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_generator_merges_candidate_audit_and_sorts_extractions(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "extracted/extract-b-model-1.0-1.0-20260714000000000000.json",
        {
            "schema_version": "1.0",
            "run_id": "extract-b-model-1.0-1.0-20260714000000000000",
            "doc_id": "b",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )
    _write_json(
        data_root / "extracted/extract-b-model-1.0-1.0-20260714000000000000-candidate-audit.json",
        {
            "run_id": "extract-b-model-1.0-1.0-20260714000000000000",
            "doc_id": "b",
            "model_name": "model",
            "prompt_version": "1.0",
            "schema_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )
    _write_json(
        data_root / "extracted/extract-a-model-1.0-1.0-20260713000000000000.json",
        {
            "schema_version": "1.0",
            "run_id": "extract-a-model-1.0-1.0-20260713000000000000",
            "doc_id": "a",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-13T00:00:00+00:00",
            "chunks": [],
        },
    )

    manifest, readme = generate_artifacts(data_root)

    assert [item["doc_id"] for item in manifest["extractions"]] == ["a", "b"]
    assert "candidate_audit_path" in manifest["extractions"][1]
    assert readme.count("<table>") == 3
    assert "candidate-audit" in readme


def test_generator_rejects_candidate_audit_with_wrong_doc_id(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "extracted/extract-doc-model-1.0-1.0-20260714000000000000.json",
        {
            "schema_version": "1.0",
            "run_id": "extract-doc-model-1.0-1.0-20260714000000000000",
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )
    _write_json(
        data_root / "extracted/extract-doc-model-1.0-1.0-20260714000000000000-candidate-audit.json",
        {
            "run_id": "extract-doc-model-1.0-1.0-20260714000000000000",
            "doc_id": "other-doc",
            "schema_version": "1.0",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )

    with pytest.raises(ValueError, match="doc_id"):
        generate_artifacts(data_root)


def test_generator_rejects_incomplete_candidate_audit_metadata(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "extracted/extract-doc-model-1.0-1.0-20260714000000000000.json",
        {
            "schema_version": "1.0",
            "run_id": "extract-doc-model-1.0-1.0-20260714000000000000",
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )
    _write_json(
        data_root / "extracted/extract-doc-model-1.0-1.0-20260714000000000000-candidate-audit.json",
        {
            "run_id": "extract-doc-model-1.0-1.0-20260714000000000000",
            "doc_id": "doc",
            "chunks": [],
        },
    )

    with pytest.raises(ValueError, match="candidate-audit schema"):
        generate_artifacts(data_root)


def test_generator_associates_known_legacy_candidate_audit(tmp_path):
    data_root = tmp_path / "data"
    run_id = "extract-doc-model-1.0-1.0-20260714000000000000"
    _write_json(
        data_root / f"extracted/{run_id}.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )
    _write_json(
        data_root / "extracted/candidate-audit.json",
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )

    manifest, _readme = generate_artifacts(data_root)

    assert manifest["extractions"][0]["candidate_audit_path"] == (
        "data/extracted/candidate-audit.json"
    )


def test_generator_merges_adjacent_identical_cells_with_rowspan(tmp_path):
    data_root = tmp_path / "data"
    for doc_id in ("a", "b"):
        _write_json(
            data_root / f"golden/golden-en-{doc_id}-1.0-1.0.json",
            {
                "schema_version": "1.0",
                "golden_version": "1.0",
                "language": "en",
                "target_group": "APT28",
                "doc_ids": [doc_id],
                "chunks": [],
                "notes": "",
            },
        )

    _manifest, readme = generate_artifacts(data_root)

    assert '<td rowspan="2">en</td>' in readme
    assert readme.index("golden/golden-en-a") < readme.index("golden/golden-en-b")


def test_generator_registers_multiple_doc_ids_in_stable_filename(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "golden/golden-en-apt28_080+apt28_081-1.0-1.0.json",
        {
            "schema_version": "1.0",
            "golden_version": "1.0",
            "language": "en",
            "target_group": "APT28",
            "doc_ids": ["apt28_081", "apt28_080"],
            "chunks": [],
            "notes": "",
        },
    )

    manifest, readme = generate_artifacts(data_root)

    assert manifest["goldens"][0]["doc_ids"] == ["apt28_080", "apt28_081"]
    assert manifest["goldens"][0]["doc_id"] == "apt28_080+apt28_081"
    assert "golden-en-apt28_080+apt28_081-1.0-1.0.json" in readme


def test_manifest_marks_generated_file_as_automatic(tmp_path):
    data_root = tmp_path / "data"

    manifest, _readme = generate_artifacts(data_root)

    assert manifest["generated_file"] is True
    assert "无需人工填写" in manifest["generated_file_notice"]


def test_generator_rejects_orphan_candidate_audit(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "extracted/extract-orphan-1.0-1.0-20260714000000000000-candidate-audit.json",
        {"run_id": "extract-orphan-1.0-1.0-20260714000000000000", "chunks": []},
    )

    try:
        generate_artifacts(data_root)
    except ValueError as exc:
        assert "孤立 candidate-audit" in str(exc)
    else:
        raise AssertionError("孤立 candidate-audit 应被拒绝")


def test_generator_rejects_mismatched_formal_artifact_filename(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "extracted/extract-other-model-1.0-1.0-20260714000000000000.json",
        {
            "schema_version": "1.0",
            "run_id": "extract-doc-model-1.0-1.0-20260714000000000000",
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-14T00:00:00+00:00",
            "chunks": [],
        },
    )

    with pytest.raises(ValueError, match="文件名与抽取结果元数据不一致"):
        generate_artifacts(data_root)


def test_generator_uses_status_and_path_as_stable_sort_keys(tmp_path):
    data_root = tmp_path / "data"
    for name, doc_id in (
        ("golden-en-a-1.0-1.0.json", "a"),
        ("golden-en-b-1.0-1.0.json", "b"),
    ):
        _write_json(
            data_root / f"golden/{name}",
            {
                "schema_version": "1.0",
                "golden_version": "1.0",
                "language": "en",
                "target_group": "APT28",
                "doc_ids": [doc_id],
                "chunks": [],
                "notes": "",
            },
        )
    manifest_path = data_root / "runs/index.json"
    _write_json(
        manifest_path,
        {
            "manifest_version": "1.0",
            "goldens": [
                {
                    "path": "data/golden/golden-en-a-1.0-1.0.json",
                    "artifact_status": "legacy",
                },
                {
                    "path": "data/golden/golden-en-b-1.0-1.0.json",
                    "artifact_status": "current",
                },
            ],
        },
    )

    manifest, _readme = generate_artifacts(data_root)

    assert [item["artifact_status"] for item in manifest["goldens"]] == ["legacy", "current"]
