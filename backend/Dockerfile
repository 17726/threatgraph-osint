ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.13-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --retries 5 -r /app/backend/requirements.txt

COPY backend /app/backend
COPY scripts /app/scripts
COPY docs/schemas /app/docs/schemas
COPY docs/prompts /app/docs/prompts
COPY data/examples /app/data/examples
COPY data/documents /app/data/documents
COPY data/golden /app/data/golden
COPY data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json /app/data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
