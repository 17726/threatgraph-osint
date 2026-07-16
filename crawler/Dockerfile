ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.13-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY crawler/requirements.txt /app/crawler/requirements.txt
RUN pip install --no-cache-dir --retries 5 -r /app/crawler/requirements.txt
RUN python -m playwright install --with-deps chromium

COPY crawler /app/crawler
COPY scripts /app/scripts

CMD ["uvicorn", "crawler.app.main:app", "--host", "0.0.0.0", "--port", "8100"]
