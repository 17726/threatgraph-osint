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
> The current version satisfies the course acceptance requirements. Standard document import, three-source collection, `reviewed` / `live` extraction, candidate validation, normalization, SQLite graph queries, behavior and MITRE analysis, five-section reports, and frontend presentation form a demonstrable end-to-end loop. Full evaluation tooling, Neo4j multidimensional queries, scheduling, and report export are optional follow-up enhancements.

## Capabilities

| Capability | Status | Description |
| --- | --- | --- |
| Target switching | Implemented | Query the SQLite canonical graph for APT28, Lazarus, and Kimsuky; an empty database returns an empty graph |
| Knowledge graph visualization | Implemented | 2D/3D switching, fullscreen, display depth (1-20), time filtering, technique/region filters, and path tracking |
| Entity and relationship details | Implemented | Types, confidence, validation status, and evidence |
| Behavior analysis | Implemented | Behavior patterns, MITRE ATT&CK mappings, inferred relationships, and threat assessment endpoints |
| Evaluation results | Backend scripts implemented | Candidate audit and development-set Precision, Recall, and F1 calculation; the main frontend focuses on graph, analysis, and reports |
| FastAPI API | P0 interfaces implemented | Document import, Pipeline, graph, path, analysis, and report endpoints |
| SQLite canonical store | Established | The authoritative source for project data |
| Document and extraction contracts | Frozen | JSON Schema, examples, and relationship matrix |
| Three-source collection | Implemented | The crawler container collects and promotes standard documents; backend performs import, live extraction, validation, and graph construction |
| Neo4j graph projection | Basic capability implemented | Full rebuild, idempotent incremental sync, status checks, and multi-hop path queries with automatic SQLite fallback |

### Core Principles

- **SQLite is the single source of truth.** Documents, chunks, extraction results, entities, relationships, evidence, and analysis results are authoritative in SQLite.
- **Git JSON stores reviewed experiment inputs and archives.** Human inputs, promoted experiments, and reviewed baselines are kept as versioned JSON artifacts; runtime canonical data remains in SQLite.
- **Candidate and canonical graph layers are separate.** LLM output enters candidate tables first and is normalized and validated before promotion.
- **Evidence is part of the analysis chain.** Entities, relationships, behavior analysis, and reports should be traceable through `evidence_ids`.
- **`graph.json` is an export snapshot.** It supports offline examples, demos, and Neo4j synchronization; it does not replace SQLite.
- **Neo4j is a rebuildable query projection.** It receives only validated entities and relationships from the SQLite canonical graph; sync failures cannot contaminate SQLite.
- **The frontend uses FastAPI.** React does not directly read SQLite, `graph.json`, or Neo4j.

## Preview

![ThreatGraph-OSINT frontend](docs/assets/pr3-frontend.png)

The frontend currently provides two main views:

- **Knowledge Graph:** Explore target entities, relationships, time ranges, and evidence.
- **Behavior Analysis:** View attack stages, MITRE ATT&CK techniques, and behavior patterns.

The graph view supports switching between 2D ECharts and a white-background 3D force-directed graph. It also provides fullscreen display, neighbor expansion, display depth, timeline, technique filters, region filters, and path tracking. The “Collect Intelligence” entry creates a crawler task through the backend; when valid LLM configuration is missing, the button is disabled and no crawler task is started.

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
| Frontend | React 19, TypeScript, Vite, ECharts, react-force-graph-3d, Three.js, Lucide React |
| Backend | FastAPI, Python 3.13 |
| Collection | Independent crawler container, HTTP/HTTPS proxy, and source adapters |
| Data | SQLite |
| Graph enhancement | Neo4j 5 Community, optional P1 layer |
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

The default startup only creates SQLite tables and does not inject demo data. Real extraction uses DeepSeek V4 Flash by default. Store `LLM_API_KEY` only in the local `.env` file. Do not place secrets in commands, source files, logs, screenshots, or commits.

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

The crawler service at `crawler:8100` exposes an HTTP API only on the Docker Compose internal network and is not published to the host. The browser can access the backend on port `8000`, but not the crawler directly. The frontend collection flow is: frontend requests a task from backend, backend calls the crawler and polls its status, crawler sends each promoted document to `/api/v1/documents/import`, and then reuses `/api/v1/pipeline/run` with `extraction_mode=live` and `/api/v1/pipeline/status/{job_id}` for extraction, validation, normalization, and graph construction.

Because collection always uses the live Pipeline, `LLM_MODEL`, `LLM_BASE_URL`, and `LLM_API_KEY` must all be non-empty in `.env`. Without valid configuration, the “Collect Intelligence” button remains visible but disabled, and the backend returns `503 ERR_LLM_NOT_CONFIGURED` without starting the crawler.

### 3. Import real extraction results

After startup, the database is empty. To call the LLM, import results into SQLite, and export a graph snapshot:

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/your-document.json \
  --import --export-graph --json
```

Existing `document.json` and `extraction_result.json` files can also be imported:

```bash
docker compose run --rm backend python scripts/import_extraction_result.py \
  --document data/documents/apt28/your-document.json \
  --extraction-result data/extracted/your-extraction-result.json \
  --export-graph
```

Generated or updated files include:

```text
SQLite database: data/threatgraph_osint.db
Graph snapshot:  data/graph/graph.json
Run summary:     data/run_logs/run-log-<run_id>.json
```

Live Pipeline runs write Extraction and Candidate Audit artifacts to `data/run_artifacts/` and task summaries to `data/run_logs/pipeline-run-<job_id>.json`. These runtime files are ignored by Git and are not automatically consumed by `reviewed` mode. Only artifacts reviewed, moved to `data/extracted/`, and registered in `config/reviewed-extractions.json` or the course demo manifest are treated as approved inputs.

After a successful SQLite write, the Pipeline attempts to advance the Neo4j projection. If Neo4j is unavailable, the SQLite task remains successful and the result reports the projection status. On first use, or after clearing Neo4j data, run:

```bash
curl -X POST http://localhost:8000/api/v1/neo4j/rebuild
curl http://localhost:8000/api/v1/neo4j/status
```

Manual idempotent incremental synchronization is also available:

```bash
curl -X POST http://localhost:8000/api/v1/neo4j/sync
```

`GET /api/v1/graph/path` prefers Neo4j when the projection is ready and synchronized. Connection failures, query failures, an uninitialized projection, or pending changes trigger an automatic SQLite fallback with a `fallback_reason`.

### 4. Stop the services

```bash
docker compose down
```

To also remove Neo4j Docker volumes:

```bash
docker compose down -v
```

## API Entry Points

The current backend provides these main endpoints:

```text
GET /api/v1/health
GET /api/v1/graph?target=APT28&depth=2
GET /api/v1/graph/neighbors?entity_id=technique:t1566&depth=2
GET /api/v1/graph/path?source=apt_group:apt28&target=malware:x-agent
GET /api/v1/analysis/{target_group}/behavior
GET /api/v1/analysis/{target_group}/mitre
GET /api/v1/analysis/{target_group}/inferences
GET /api/v1/analysis/{target_group}/threat-assessment
POST /api/v1/pipeline/run
GET /api/v1/pipeline/status/{job_id}
GET /api/v1/neo4j/status
POST /api/v1/neo4j/rebuild
POST /api/v1/neo4j/sync
GET /api/v1/reports/{target_group}
POST /api/v1/reports/{target_group}/generate
POST /api/v1/crawl/runs
GET /api/v1/crawl/runs/{crawl_run_id}
```

Successful responses use this shape:

```json
{
  "success": true,
  "data": {},
  "timestamp": "2026-07-12T00:00:00+08:00"
}
```

See [`docs/api-contract.md`](docs/api-contract.md) for complete fields, error codes, and endpoint semantics.

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
  --golden data/golden/golden-en-apt28_080-1.0-1.0.json \
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

### Crawler tests

```bash
docker compose build crawler
docker compose run --rm crawler python -m pytest crawler/tests -v
```

### Frontend tests and build

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```

The frontend `App` integrates graph, analysis, reports, Pipeline, and collection entry points. `EvaluationPage` and historical evaluation data remain in the repository, while evaluation metrics are documented by backend scripts and development-set reports.

### Validate an extraction result

```bash
docker compose run --rm backend python scripts/validate_extraction_result.py \
  data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json \
  --document data/examples/document.apt28.thn.beardshell.example.json
```

## Project Structure

```text
.
├── backend/              FastAPI backend and services
├── crawler/              Independent collection service and source adapters
├── frontend/             React + TypeScript + Vite frontend
├── data/
│   ├── examples/         Contract examples
│   ├── documents/        Standardized source documents
│   ├── extracted/        Extraction results
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
| [`docs/demo-flow.md`](docs/demo-flow.md) | Course demonstration flow and implementation boundaries |
| [`docs/schemas/README.md`](docs/schemas/README.md) | JSON Schemas and examples |
| [`docs/docker-runtime.md`](docs/docker-runtime.md) | Docker Compose runtime contract |
| [`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md) | Real LLM extraction and evaluation workflow |
| [`docs/reports/llm-extraction-baseline.md`](docs/reports/llm-extraction-baseline.md) | DeepSeek V4 baseline and evaluation limitations |
| [`docs/team-workflow.md`](docs/team-workflow.md) | Team responsibilities and workflow |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | Development conventions and Git workflow |

New members should read the documentation in this order:

1. This README for the project scope and runtime entry points.
2. [`TODO.md`](TODO.md) for current progress and task boundaries.
3. [`docs/stage-roadmap.md`](docs/stage-roadmap.md) for the project phases.
4. [`docs/architecture.md`](docs/architecture.md) for the system data flow.
5. The contract and workflow documents for the responsible team.

Recommended entry points by team:

| Team | Recommended reading |
| --- | --- |
| Architecture and data `arch` | [`docs/architecture.md`](docs/architecture.md), [`docs/api-contract.md`](docs/api-contract.md), [`docs/data-contract.md`](docs/data-contract.md) |
| Data and samples `data` | [`docs/data-contract.md`](docs/data-contract.md), [`docs/schemas/README.md`](docs/schemas/README.md), [`docs/team-workflow.md`](docs/team-workflow.md) |
| LLM extraction and analysis `llm` | [`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md), [`docs/data-contract.md`](docs/data-contract.md), [`docs/schemas/README.md`](docs/schemas/README.md) |
| Graph and frontend `fe` | [`docs/api-contract.md`](docs/api-contract.md), [`docs/team-workflow.md`](docs/team-workflow.md) |
| QA, reports, and defense `qa` | [`docs/team-workflow.md`](docs/team-workflow.md), [`docs/reference-comparison.md`](docs/reference-comparison.md), [`docs/references/course-requirements.md`](docs/references/course-requirements.md) |

## Current Roadmap

```text
Step 0  Scaffold and mock loop             Complete
Step 1  Real document loop                 Complete
Step 2  P0 MVP loop                        Complete
Step 3  Course acceptance loop             Complete
Step 4  Neo4j, collection, and reporting  P1 follow-up enhancements
```

The current version uses APT28, Kimsuky, and Lazarus samples from three public-source categories to complete the course demonstration loop: collection/import, candidate extraction, normalization, canonical graph construction, behavior/MITRE analysis, structured reports, and frontend presentation. Follow-up work includes Neo4j multidimensional queries, scheduled collection, incremental updates, report export, and more complete evaluation tooling.

## Data and Privacy

- Do not commit original course PDFs.
- Do not commit unsanitized chat records, private URLs, instructor contact details, or personal contact information.
- Do not commit API keys, real passwords, or `.env` files. Keep secrets in local environment files only.
- Keep public materials limited to necessary course requirements and sanitized project data.
