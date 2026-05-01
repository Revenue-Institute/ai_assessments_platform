FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /usr/local/bin/

# Build context is the repo root so the API can read shared data files
# (e.g. packages/competencies/src/taxonomy.json) at runtime. The runtime
# image keeps /app as the service root and bundles the few shared
# packages it reads at runtime under /repo so the path-resolution
# helpers (which expect a repo-shaped layout) keep working.

WORKDIR /app

COPY apps/api/pyproject.toml /app/pyproject.toml
RUN uv sync --no-install-project --no-dev

COPY apps/api/src /app/src
RUN uv sync --no-dev

# Generator's _load_taxonomy_text() walks Path(__file__).parents[4],
# which resolves to "/" inside the image; place shared data at /packages
# to match.
COPY packages/competencies /packages/competencies

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "ri_assessments_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
