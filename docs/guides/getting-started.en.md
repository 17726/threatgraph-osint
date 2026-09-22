# Getting started

This guide covers setup, the reviewed sample, model integration, and development checks. See the [README](../../README.en.md) for the project overview.

## Run locally

Install **Git** and **Docker with Compose** (Docker Desktop on Windows / macOS). The container workflow does not require a local Python or Node.js installation.

### 1. Get the code

```bash
git clone https://github.com/17726/threatgraph-osint.git
cd threatgraph-osint
cp .env.example .env
```

In Windows PowerShell, replace the last line with:

```powershell
Copy-Item .env.example .env
```

Leave `LLM_API_KEY` empty to try the local sample.

### 2. Start the core services

```bash
docker compose up --build -d backend frontend
```

| Entry point                   | URL                                   |
| ----------------------------- | ------------------------------------- |
| Frontend                      | <http://localhost:5173>               |
| Interactive API documentation | <http://localhost:8000/docs>          |
| Health check                  | <http://localhost:8000/api/v1/health> |

Startup initializes the database but **does not seed sample data**. Basic browsing and offline imports do not require the crawler, Neo4j, or a model API.

### 3. Import the reviewed sample

Run this single-line command from the repository root (works in Bash and PowerShell). Both the document and the manually reviewed extraction are included:

```bash
docker compose run --rm backend python scripts/import_extraction_result.py --document data/examples/document.apt28.thn.beardshell.example.json --extraction-result data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json --export-graph --json
```

This does not call a model API. Open the frontend, select **APT28**, and click refresh (刷新). Select nodes or relationships to inspect evidence. This sample populates only APT28; Lazarus and Kimsuky need their own document/extraction pairs.

Data persists on the host at `data/threatgraph_osint.db`, with an exported snapshot at `data/graph/graph.json`. The frontend reads the database-backed graph through FastAPI.

### 4. Stop the services

```bash
docker compose down
```

SQLite data in the local `data/` directory is retained. Restart with `docker compose up -d backend frontend`.

## Models and collection

Configure your provider in the local `.env` file. The repository example uses DeepSeek defaults; replace them with your own OpenAI-compatible provider settings if needed:

```dotenv
LLM_API_KEY=<your API key>
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

Model names and availability depend on your provider. The preflight, live extraction, and collection steps below call an external model API and incur provider charges.

Check connectivity:

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py --preflight-only --json
```

Extract from an included document, import the result, and export the graph:

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py --document data/documents/apt28/apt28_080.json --import --export-graph --json
```

To collect new intelligence through the UI, start the crawler and apply the environment configuration:

```bash
docker compose up --build -d backend frontend crawler
```

Click “采集情报” in the frontend. Collection always uses `live` extraction. Without model configuration, the button is disabled and the API returns `503 ERR_LLM_NOT_CONFIGURED`. The crawler communicates with the backend over the internal network and exposes no host port.

A document-level filtering failure allows other documents to continue, with the task marked `partial_success`. See the [extraction and evaluation guide](../guides/llm-extraction-and-evaluation.md) for settings and metric definitions, and [running and troubleshooting](../guides/running-and-troubleshooting.md) for logs, artifacts, and optional Neo4j setup. Detailed guides are currently in Chinese.

## Development and verification

```text
backend/       FastAPI, graph queries, extraction, analysis, and tests
frontend/      Graph interaction, analysis, reports, and task progress
crawler/       Separate collection service and tests
scripts/       Conversion, extraction, import, export, and evaluation
config/        Reviewed artifact manifests and sample configuration
data/          Standard documents, Golden data, artifacts, and local runtime data
docs/          Architecture, contracts, guides, and research records
```

Backend and crawler tests:

```bash
docker compose build backend crawler
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm crawler python -m pytest crawler/tests -v
```

Frontend tests, build, and formatting:

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```
