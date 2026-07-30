FROM python:3.10-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project definition
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv pip install --system -r pyproject.toml

# Copy application code
COPY api/ api/
COPY config/ config/
COPY data/canonical/ data/canonical/

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
