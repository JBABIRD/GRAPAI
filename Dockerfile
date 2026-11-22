FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/ductus ./ductus
COPY backend/comfy_workflows ./comfy_workflows
RUN pip install --no-cache-dir .
COPY --from=web /app/frontend/dist /app/frontend/dist
ENV DUCTUS_DATA_DIR=/data DUCTUS_COMFY_WORKFLOWS=/app/backend/comfy_workflows DUCTUS_WEB_DIR=/app/frontend/dist
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "ductus.api:app", "--host", "0.0.0.0", "--port", "8000"]
