# Bulletin Maker — hosted container (Cloud Run / HF Spaces / any Docker host)
#
# Build:  docker build -t bulletin-maker .
# Run:    docker run -p 8080:8080 bulletin-maker
#
# The same FastAPI app the local `bulletin-maker` command runs; nothing
# hosted-specific in the application code. Scale-to-zero friendly: no
# state outside the container except per-session memory.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

# Chromium + its system dependencies via Playwright's supported path,
# into a fixed world-readable location (set above) so it works for the
# non-root runtime user.
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

# Non-root runtime user with a writable HOME for ~/.bulletin-maker caches
RUN useradd --create-home app
USER app
ENV HOME=/home/app

# Cloud Run injects $PORT (defaults to 8080)
EXPOSE 8080
CMD ["sh", "-c", "uvicorn --factory bulletin_maker.web.server:create_app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
