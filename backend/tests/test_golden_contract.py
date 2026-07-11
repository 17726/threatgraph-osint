from pathlib import Path

import pytest

from scripts.validate_golden import validate_golden_file


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CASES = [
    (
        ROOT / "data/evaluation/golden.en.apt28_080.json",
        [ROOT / "data/documents/apt28/apt28_080.json"],
    ),
    (
        ROOT / "data/evaluation/golden.en.kimsuky_060.json",
        [ROOT / "data/documents/kimsuky/kimsuky_060.json"],
    ),
]


@pytest.mark.parametrize(("golden_path", "document_paths"), GOLDEN_CASES)
def test_formal_golden_matches_contract_matrix_and_documents(
    golden_path, document_paths
):
    report = validate_golden_file(golden_path, document_paths=document_paths)

    assert report.ok, "\n".join(report.errors)
