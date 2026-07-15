import json
from pathlib import Path

from scripts.run_llm_extraction import run_single


class FakeExtractionService:
    model = "test-model"
    last_warnings: list[str] = []
    last_candidate_audit = {"chunks": []}
    last_api_observation = {
        "calls": 1,
        "duration_ms": 12.5,
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    def extract(self, document: dict, prompt_version: str) -> dict:
        return {
            "schema_version": "1.0",
            "run_id": "extract-test-doc-test-model-1.0-1.0-test",
            "doc_id": document["doc_id"],
            "model_name": self.model,
            "prompt_version": prompt_version,
            "generated_at": "2026-07-16T00:00:00+00:00",
            "chunks": [{"chunk_id": "test_doc_c001", "entities": [], "relations": []}],
        }

    def save_result(self, result: dict, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "extraction.json"
        output_path.write_text(json.dumps(result), encoding="utf-8")
        return output_path

    def save_candidate_audit(self, output_dir: Path) -> Path:
        output_path = output_dir / "candidate-audit.json"
        output_path.write_text(json.dumps(self.last_candidate_audit), encoding="utf-8")
        return output_path


def test_run_single_writes_structured_timing_log(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "test_doc", "clean_text": "APT28 used malware."}),
        encoding="utf-8",
    )
    log_dir = tmp_path / "run_logs"

    summary = run_single(
        document_path,
        FakeExtractionService(),
        output_dir=tmp_path / "extracted",
        run_log_dir=log_dir,
    )

    assert summary["status"] == "succeeded"
    assert summary["timing"]["document_load_ms"] >= 0
    assert summary["timing"]["llm_ms"] >= 0
    assert summary["timing"]["evaluation_ms"] is None
    assert summary["timing"]["sqlite_import_ms"] is None
    assert summary["timing"]["graph_export_ms"] is None
    assert summary["timing"]["total_ms"] >= summary["timing"]["llm_ms"]
    assert summary["llm"]["usage"]["total_tokens"] == 15

    log_path = Path(summary["run_log"])
    assert log_path.parent == log_dir
    assert log_path.name == f"run-log-{summary['run_id']}.json"
    saved_log = json.loads(log_path.read_text(encoding="utf-8"))
    assert saved_log["run_id"] == summary["run_id"]
    assert saved_log["timing"] == summary["timing"]
    assert saved_log["llm"] == summary["llm"]
