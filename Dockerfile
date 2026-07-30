# Stage 1: Build Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Backend
FROM python:3.10-slim
WORKDIR /app

# Install uv
RUN pip install uv

# Copy project definition
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv pip install --system -r pyproject.toml

# Copy backend code
COPY api/ api/
COPY config/ config/
COPY data/canonical/ data/canonical/

# Copy built frontend from Stage 1
COPY --from=frontend-builder /frontend/dist /app/api/static

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
