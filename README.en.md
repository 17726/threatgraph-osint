# ThreatGraph-OSINT

<div align="center">

**Open-Source Threat Intelligence Knowledge Graph Investigation System**

An evidence-aware OSINT analysis platform for APT organizations, entity relationships, and behavior patterns.

[简体中文](README.md) | English

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=111827)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)

[Quick Start](#quick-start) · [Capabilities](#capabilities) · [Architecture](#architecture) · [Documentation](#documentation) · [Verification](#verification)

</div>

ThreatGraph-OSINT turns public threat intelligence documents into a searchable, visual, and traceable knowledge graph. It is designed for investigating APT28, Lazarus, Kimsuky, and related entities, relationships, evidence, behavior patterns, and evaluation results.

The project is developed for Experiment 3 of the Network Cyberspace Security Comprehensive Experiment course: **deep analysis of potential behaviors and relationships in open-source intelligence using large language models**.

> [!IMPORTANT]
> The repository is currently in the P0 / Step 1 iteration. The graph UI, basic behavior analysis, offline extraction validation, and real LLM extraction workflow are available. The complete multi-source document loop, automated collection, and Neo4j query enhancement are still being developed.

## Capabilities

| Capability | Status | Description |
| --- | --- | --- |
| Target switching | Implemented | Demo data for APT28, Lazarus, and Kimsuky |
| Knowledge graph visualization | Implemented | Entities, relationships, time filtering, and path tracking |
| Entity and relationship details | Implemented | Types, confidence, validation status, and evidence |
| Behavior analysis | Basic page implemented | Attack stages, technique mapping, and analysis display |
| Evaluation results | Mock page implemented | Evaluation UI prototype and sample error cases; metrics are frontend mock data |
| FastAPI API | P0 interfaces implemented | Health, graph, and report endpoints |
| SQLite canonical store | Established | The authoritative source for project data |
| Document and extraction contracts | Frozen | JSON Schema, examples, and relationship matrix |
| Automated collection | Planned | HTTP pages and RSS/Atom sources are planned |
| Neo4j path queries | P1 enhancement | An optional query layer backed by the SQLite canonical graph |

### Core Principles

- **SQLite is the single source of truth.** Documents, chunks, extraction results, entities, relationships, evidence, and analysis results are authoritative in SQLite.
- **Candidate and canonical graph layers are separate.** LLM output enters candidate tables first and is normalized and validated before promotion.
- **Evidence is part of the analysis chain.** Entities, relationships, behavior analysis, and reports should be traceable through `evidence_ids`.
- **`graph.json` is an export snapshot.** It supports offline examples, demos, and Neo4j synchronization; it does not replace SQLite.
- **The frontend uses FastAPI.** React does not directly read SQLite, `graph.json`, or Neo4j.

## Preview

![ThreatGraph-OSINT frontend](docs/assets/pr3-frontend.png)

The frontend currently provides three main views:

- **Knowledge Graph:** Explore target entities, relationships, time ranges, and evidence.
- **Behavior Analysis:** View attack stages, MITRE ATT&CK techniques, and behavior patterns.
- **Evaluation:** View the evaluation page prototype, mock metrics, and error examples.

## Architecture

```text
Public intelligence / cleaned local documents
                    |
                    v
             Document import and chunking
                    |
                    v
             LLM candidate extraction
                    |
                    v
       Validation, normalization, and evidence binding
                    |
                    v
                 SQLite
                    |
              +-----+-----+
              v           v
        graph.json      FastAPI
              |           |
              v           v
        Neo4j         React + ECharts
       P1 enhancement   Investigation UI
```

### Technology Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, ECharts, Lucide React |
| Backend | FastAPI, Python 3.13 |
| Data | SQLite |
| Graph enhancement | Neo4j 5 Community, planned for P1 |
| Runtime | Docker Compose |
| LLM interface | OpenAI-compatible API, DeepSeek V4 Flash by default |

## Quick Start

### Prerequisites

- Docker Desktop with Docker Compose
- Git

The recommended workflow uses Docker Compose and does not require local Python or frontend dependency installation.

### 1. Configure the environment

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Demo data does not require an LLM API key. Real extraction uses DeepSeek V4 Flash by default. Store `LLM_API_KEY` only in the local `.env` file. Do not place secrets in commands, source files, logs, screenshots, or commits.

### 2. Start the services

For the first start or after dependency changes:

```bash
docker compose up --build
```

For later starts:

```bash
docker compose up
```

Service URLs:

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend API | <http://localhost:8000> |
| Swagger API docs | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/api/v1/health> |
| Neo4j Browser | <http://localhost:7474> |

### 3. Seed and export demo data

Run these commands in another terminal:

```bash
docker compose run --rm backend python scripts/seed_demo_data.py
docker compose run --rm backend python scripts/export_graph_json.py
```

Generated files:

```text
SQLite database: data/threatgraph_osint.db
Graph snapshot:  data/graph/graph.json
```

### 4. Stop the services

```bash
docker compose down
```

To also remove Neo4j Docker volumes:

```bash
docker compose down -v
```

## API Entry Points

The current P0 backend provides these basic endpoints:

```text
GET /api/v1/health
GET /api/v1/graph?target=APT28&depth=2
GET /api/v1/reports/{target_group}
```

Successful responses use this shape:

```json
{
  "success": true,
  "data": {},
  "timestamp": "2026-07-12T00:00:00+08:00"
}
```

See [`docs/api-contract.md`](docs/api-contract.md) for complete fields, error codes, and planned endpoints.

## Data Contracts

The project uses a schema-first workflow for cross-team data boundaries:

```text
data/documents/<target_group>/*.json
              |
              v
       document.schema.json
              |
              v
   extraction-result.schema.json
              |
              v
 Validation, normalization, and evidence binding
              |
              v
 graph.schema.json -> data/graph/graph.json
```

Key contract files:

- [`document.schema.json`](docs/schemas/document.schema.json): Cleaned standard documents.
- [`extraction-result.schema.json`](docs/schemas/extraction-result.schema.json): LLM candidate entities and relationships.
- [`golden.schema.json`](docs/schemas/golden.schema.json): Human-annotated evaluation data.
- [`graph.schema.json`](docs/schemas/graph.schema.json): Complete graph snapshots exported from SQLite.
- [`relationship-matrix.md`](docs/schemas/relationship-matrix.md): Valid entity and relationship type combinations.

Reusable examples are stored in [`data/examples/`](data/examples/). Real cleaned documents use `data/documents/<target_group>/`.

## Real LLM Extraction and Evaluation

Configure `LLM_API_KEY` in the local `.env` file, then run a minimal connectivity check:

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --preflight-only --json
```

Run extraction and evaluate against an annotated golden document:

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/apt28_080.json \
  --golden data/evaluation/golden.en.apt28_080.json \
  --json
```

Candidate results remain separate from the canonical graph. Filtered raw candidates are written to `candidate-audit.json` and counted as false positives during evaluation. To import validated candidates into SQLite and export a graph snapshot, explicitly add `--import --export-graph`.

For the full workflow and evaluation policy, see [`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md).

## Verification

### Backend tests

```bash
docker compose build backend
docker compose run --rm backend python -m pytest backend/tests -v
```

### Frontend tests and build

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```

### Validate an extraction result

```bash
docker compose run --rm backend python scripts/validate_extraction_result.py \
  data/extracted/extraction_result.apt28.thn.beardshell.v1.json \
  --document data/documents/apt28/apt28_049.json
```

## Project Structure

```text
.
├── backend/              FastAPI backend and services
├── frontend/             React + TypeScript + Vite frontend
├── data/
│   ├── examples/         Contract examples
│   ├── documents/        Standardized source documents
│   ├── extracted/        Extraction results
│   ├── evaluation/       Golden data and evaluation results
│   ├── graph/            graph.json export snapshots
│   └── threatgraph_osint.db
├── scripts/              Import, extraction, validation, and export scripts
├── docs/                 Architecture, contracts, guides, and reports
├── TODO.md               Current tasks and project progress
└── docker-compose.yml    Local development orchestration
```

## Documentation

| Document | Purpose |
| --- | --- |
| [`README.md`](README.md) | Chinese project overview and quick start |
| [`TODO.md`](TODO.md) | Current progress, priorities, and next tasks |
| [`docs/stage-roadmap.md`](docs/stage-roadmap.md) | Step 0 to Step 4 roadmap and acceptance criteria |
| [`docs/architecture.md`](docs/architecture.md) | Architecture, data flow, and boundaries |
| [`docs/api-contract.md`](docs/api-contract.md) | FastAPI contract |
| [`docs/data-contract.md`](docs/data-contract.md) | SQLite data contract |
| [`docs/schemas/README.md`](docs/schemas/README.md) | JSON Schemas and examples |
| [`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md) | Real LLM extraction and evaluation workflow |
| [`docs/reports/llm-extraction-baseline.md`](docs/reports/llm-extraction-baseline.md) | DeepSeek V4 baseline and evaluation limitations |
| [`docs/docker-runtime.md`](docs/docker-runtime.md) | Docker Compose runtime contract |
| [`docs/team-workflow.md`](docs/team-workflow.md) | Team responsibilities and workflow |

## Current Roadmap

```text
Step 0  Scaffold and mock loop             Complete
Step 1  Real document loop                 In progress
Step 2  P0 MVP loop                        Pending
Step 3  Course acceptance loop             Pending
Step 4  Neo4j, collection, and reporting  Planned
```

The immediate goal is to run at least one traceable real document through import, chunking, candidate extraction, normalization, canonical graph construction, and frontend display.

## Data and Privacy

- Do not commit original course PDFs.
- Do not commit unsanitized chat records, private URLs, instructor contact details, or personal contact information.
- Do not commit API keys, real passwords, or `.env` files. Keep secrets in local environment files only.
- Keep public materials limited to necessary course requirements and sanitized project data.
