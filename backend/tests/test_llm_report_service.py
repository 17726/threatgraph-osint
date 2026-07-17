import sqlite3

from backend.app.services.llm_report_service import LLMReportService


def test_report_prompt_contains_attack_chain_section(tmp_path):
    connection = sqlite3.connect(tmp_path / "graph.db")
    connection.executescript(
        """
        CREATE TABLE entities (
          entity_id TEXT PRIMARY KEY, name TEXT, type TEXT,
          aliases_json TEXT, description TEXT, confidence REAL,
          source_count INTEGER, first_seen TEXT, last_seen TEXT
        );
        CREATE TABLE relations (
          relation_id TEXT PRIMARY KEY, source_entity_id TEXT, target_entity_id TEXT,
          relation_type TEXT, label TEXT, confidence REAL, evidence_count INTEGER,
          first_seen TEXT, last_seen TEXT
        );
        CREATE TABLE evidence (
          evidence_id TEXT PRIMARY KEY, entity_id TEXT, relation_id TEXT,
          evidence_text TEXT, source_name TEXT, published_at TEXT
        );
        CREATE TABLE behavior_patterns (
          target_group TEXT, stage TEXT, description TEXT,
          technique_ids_json TEXT, confidence REAL
        );
        CREATE TABLE mitre_mappings (
          target_group TEXT, technique_id TEXT, technique_name TEXT,
          tactic TEXT, attack_stage TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("apt_group:apt28", "APT28", "APT_GROUP", "[]", "", 0.9, 1, "2020", "2024"),
    )
    connection.commit()
    connection.close()

    service = LLMReportService(db_path=tmp_path / "graph.db")
    prompt = service._build_prompt("APT28")

    assert "6. ## attack_chain" in prompt
    assert "攻击链分析" in prompt


def test_parse_sections_includes_attack_chain_as_sixth_section():
    service = LLMReportService()
    sections = service._parse_sections(
        "\n".join(
            [
                "## profile\n画像",
                "## behavior_patterns\n行为",
                "## network\n网络",
                "## timeline\n时间",
                "## threat_assessment\n评估",
                "## attack_chain\n攻击链叙事",
            ]
        )
    )

    assert len(sections) == 6
    assert sections[5]["section_type"] == "attack_chain"
    assert sections[5]["markdown"] == "攻击链叙事"
