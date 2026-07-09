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
COPY data/examples /app/data/examples
COPY data/extracted/extraction_result.apt28.thn.beardshell.v1.json /app/data/extracted/extraction_result.apt28.thn.beardshell.v1.json

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
