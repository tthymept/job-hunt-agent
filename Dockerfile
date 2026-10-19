# One container runs everything: FastAPI serves both /api and the built React app.

# ---- Stage 1: build the React app into front-end/dist ----
FROM node:22-slim AS frontend
WORKDIR /app/front-end
COPY front-end/package.json front-end/package-lock.json ./
RUN npm ci
COPY front-end/ ./
RUN npm run build

# ---- Stage 2: the Python backend ----
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /bin/uv
WORKDIR /app

# Install dependencies first (cached until pyproject.toml / uv.lock change)
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the code: the root-level agents, the API package, and the built frontend
COPY *.py ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=frontend /app/front-end/dist ./front-end/dist

# Render sets PORT; 8000 is the fallback for running the image yourself
CMD ["sh", "-c", "uv run --no-sync uvicorn job_hunt_agent.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
