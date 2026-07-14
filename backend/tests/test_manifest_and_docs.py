import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_registers_historical_evaluation():
    manifest = json.loads((ROOT / "data/runs/index.json").read_text(encoding="utf-8"))

    evaluations = manifest["evaluations"]
    assert len(evaluations) == 1
    assert evaluations[0]["path"] == (
        "data/evaluation/evaluation_result.apt28_080.deepseek-v4-flash.extract-v1.json"
    )
    assert evaluations[0]["artifact_status"] == "legacy"


def test_baseline_report_marks_lazarus_boundary_as_historical():
    report = (ROOT / "docs/reports/llm-extraction-baseline.md").read_text(encoding="utf-8")

    assert "历史基线运行时" in report
    assert "后续" in report
    assert "当前文件已迁移至 data/golden/" in report


def test_dockerignore_does_not_keep_old_golden_exception():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "!data/evaluation/golden*.json" not in dockerignore


def test_data_artifact_action_only_tracks_source_directories():
    workflow = (ROOT / ".github/workflows/sync-data-artifacts.yml").read_text(encoding="utf-8")

    assert "branches:\n      - main" in workflow
    assert "data/golden/**" in workflow
    assert "data/extracted/**" in workflow
    assert "data/evaluation/**" in workflow
    assert "git diff --cached --quiet" in workflow
    assert "git add data/runs/index.json data/README.md" in workflow


def test_generator_script_bootstraps_repository_path_for_direct_execution():
    script = (ROOT / "scripts/generate_data_artifacts.py").read_text(encoding="utf-8")

    assert "sys.path.insert" in script
    assert "REPO_ROOT" in script


def test_dockerignore_keeps_candidate_audit_for_reproducible_evaluation():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "data/extracted/*-candidate-audit.json" not in dockerignore


def test_runner_validates_explicit_evaluation_output_path():
    script = (ROOT / "scripts/run_llm_extraction.py").read_text(encoding="utf-8")

    assert "validate_evaluation_artifact_filename(evaluation_output, evaluation)" in script


def test_data_artifact_workflow_runs_backend_tests():
    workflow = (ROOT / ".github/workflows/sync-data-artifacts.yml").read_text(encoding="utf-8")

    assert "python -m pytest backend/tests -v" in workflow


def test_prompt_uses_numeric_versioned_filename():
    assert (ROOT / "docs/prompts/extract-1.0.md").is_file()
    assert not (ROOT / "docs/prompts/extract-v1.md").exists()


def test_historical_baseline_declares_legacy_format():
    report = (ROOT / "docs/reports/llm-extraction-baseline.md").read_text(encoding="utf-8")

    assert "Legacy" in report
    assert "extract-v1" in report


def test_candidate_audit_schema_exists():
    schema = ROOT / "docs/schemas/candidate-audit.schema.json"

    assert schema.is_file()
