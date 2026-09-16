# RepoLens API and analysis worker.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git is required: repositories are acquired with `git clone`, never by
# executing anything from the repository itself.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install the analysis packages first so dependency layers cache well.
COPY packages/ /srv/packages/
RUN pip install \
      ./packages/shared \
      ./packages/analysis \
      ./packages/github \
      ./packages/security \
      ./packages/similarity \
      ./packages/scoring

COPY apps/api/pyproject.toml /srv/apps/api/pyproject.toml
COPY apps/api/ /srv/apps/api/
RUN pip install /srv/apps/api

WORKDIR /srv/apps/api

# Run as an unprivileged user: the process handles untrusted repository content.
RUN useradd --create-home --uid 10001 repolens \
 && chown -R repolens:repolens /srv
USER repolens

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
