# Production image for the Design Drift API.
#
# Separate from backend.Dockerfile, which is the development image: that one
# mounts the source as a volume and runs uvicorn --reload, neither of which
# belongs in a deployment.
#
# Why this is a Docker deploy and not a native Python one: the Production
# Analysis and Accessibility agents drive a real Chromium (Playwright
# capture, axe-core against the live DOM). That needs the browser binary and
# its system libraries, which a buildpack-style Python runtime does not
# provide. `playwright install --with-deps` is the supported way to get
# both, and it needs root at build time.
#
# Build context is backend/ (see render.yaml's dockerContext), and
# backend/.dockerignore keeps the developer's .venv and type caches out of
# it, without that the context carries 400MB of host-architecture binaries
# that would be layered on top of the venv this image builds for itself.

FROM python:3.12-slim

# uv resolves from the committed uv.lock, so the image gets the same
# versions CI tested rather than whatever is newest at build time.
RUN pip install --no-cache-dir uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Install browsers to a fixed path rather than $HOME/.cache, which
    # differs between the build user and the runtime user and would leave
    # Playwright unable to find the browser it just installed.
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    # The venv uv builds, on PATH, so the start command runs the installed
    # packages directly. `uv run` would re-resolve the project at startup
    # and reinstall the dev group that --no-dev deliberately excluded.
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# The unprivileged runtime user, created before anything is copied so each
# COPY can land already-owned. A trailing `chown -R` would otherwise
# duplicate every file it touches into a new layer, 1.45GB, measured.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app /data /workspaces /opt/playwright \
    && chown appuser:appuser /app /data /workspaces /opt/playwright

WORKDIR /app

# Dependencies first, in their own layer: they change far less often than
# the application code, so a code-only change reuses this layer and skips
# both the resolve and the ~400MB browser download below.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# Chromium plus the system libraries it needs. --with-deps runs apt-get, so
# it has to happen as root, before the image drops privileges. The browser
# goes to PLAYWRIGHT_BROWSERS_PATH, which appuser owns.
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache

COPY --chown=appuser:appuser . .

# Installs the project itself into the venv built above. Not combined with
# the earlier sync: that one is cached on the lockfile alone, and merging
# them would redo the whole resolve on every source change.
RUN uv sync --locked --no-dev \
    && chown -R appuser:appuser /app/.venv

# Runs as a non-root user: this process launches a browser that loads
# whatever page a project points at, so the blast radius of a Chromium
# sandbox escape should not include root in the container.
USER appuser

EXPOSE 8000

# Migrations run here rather than in a separate release step, because
# Render's free and starter tiers have no release phase. `alembic upgrade
# head` is idempotent, so a restart or a second instance is harmless.
#
# alembic/uvicorn directly, not `uv run`: the venv is on PATH, and uv run
# would re-sync at startup and pull the dev group back in.
#
# $PORT is what the platform assigns; the default keeps `docker run` working.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
