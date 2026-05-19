FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir litellm httpx "mcp[cli]" pydantic "rubric>=2.2,<3"

ENV PYTHONPATH=/usr/lib

COPY environment/diligence_bench /usr/lib/diligence_bench
