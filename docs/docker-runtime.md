# Docker 运行契约

> 适用范围：ThreatGraph-OSINT 项目  
> 标准环境：Docker Compose  
> 本地备用：后端 `uv`，前端 `pnpm`

---

## 1. 运行结论

本项目默认用 Docker Compose 管理服务：

```text
backend：FastAPI 后端
frontend：React + TypeScript + Vite 前端
neo4j：P1 图数据库
```

SQLite 不作为独立服务运行，而是项目数据文件：

```text
data/threatgraph_osint.db
```

---

## 2. 推荐端口

```text
frontend：http://localhost:5173
backend：http://localhost:8000
backend docs：http://localhost:8000/docs
neo4j browser：http://localhost:7474
neo4j bolt：bolt://localhost:7687
```

---

## 3. 环境变量

`.env.example` 至少包含：

```bash
# app
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000

# sqlite
SQLITE_DB_PATH=/app/data/threatgraph_osint.db

# llm openai-compatible
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3

# neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change_me_for_local_dev

# frontend
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## 4. docker-compose 设计

`docker-compose.yml` 应包含：

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    env_file:
      - .env
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app/backend
      - ./scripts:/app/scripts
      - ./data:/app/data
    depends_on:
      - neo4j
    command: uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    env_file:
      - .env
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app/frontend
      - /app/frontend/node_modules
    command: pnpm --dir frontend dev --host 0.0.0.0

  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/change_me_for_local_dev
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
```

说明：

1. `backend` 挂载 `data/`，读写 SQLite 和导出的 `graph.json`。
2. `frontend` 只通过 `VITE_API_BASE_URL` 调后端。
3. `neo4j` 是 P1 必做服务，但 P0 的基础图谱展示不依赖它。
4. `backend depends_on neo4j` 只保证容器启动顺序，不代表后端必须依赖 Neo4j 可用。

---

## 5. 常用命令

```bash
# 构建并启动全部服务
docker compose up --build

# 后台启动全部服务
docker compose up -d

# 启动指定服务
docker compose up backend
docker compose up frontend
docker compose up neo4j

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f neo4j

# 进入后端容器
docker compose exec backend bash

# 运行流水线
docker compose exec backend python scripts/run_pipeline.py --target APT28

# 导出 graph.json
docker compose exec backend python scripts/export_graph_json.py

# 同步 Neo4j
docker compose exec backend python scripts/sync_neo4j.py

# 停止服务
docker compose down
```

---

## 6. 本地备用运行

后端：

```bash
uv sync
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
pnpm install
pnpm --dir frontend dev
```

Neo4j：

```bash
docker compose up neo4j
```

原则：本地备用运行不能改变系统架构。事实源仍然是 SQLite，前端仍然只调 FastAPI。
