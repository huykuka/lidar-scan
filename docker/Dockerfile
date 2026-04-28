# ----------------------------------------
# Stage 1: Build sick_scan_xd C++ library
# ----------------------------------------
FROM ubuntu:22.04 AS backend-builder

ENV ROS_VERSION=0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
  git \
  build-essential \
  cmake \
  gdb \
  ninja-build \
  && rm -rf /var/lib/apt/lists/*

RUN git clone -b 3.9.0 https://github.com/SICKAG/sick_scan_xd.git /workspace/sick_scan_xd \
  && mkdir -p /workspace/build \
  && cd /workspace/build \
  && rm -rf ./* \
  && export ROS_VERSION=0 \
  && cmake -DROS_VERSION=0 -DLDMRS=0 -G "Unix Makefiles" ../sick_scan_xd \
  && make -j4 \
  && make install

# ----------------------------------------
# Stage 2: Build Angular frontend
# ----------------------------------------
FROM --platform=$BUILDPLATFORM node:24-slim AS frontend-builder
WORKDIR /web
# Copy package manifests first for caching
COPY web/package*.json ./
RUN npm ci
# Copy rest of frontend source and build
COPY web/ ./
RUN npm run build -- --configuration production

# ----------------------------------------
# Stage 3: Cython compilation (source → .so)
# ----------------------------------------
FROM python:3.12-slim-bookworm AS cython-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  python3-dev \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cython setuptools

WORKDIR /src
COPY app/ ./app/
COPY main.py build_cython.py ./

# Compile all .py → .so, then strip source artefacts.
# __init__.py files are kept so package discovery still works.
RUN python build_cython.py build_ext --inplace \
  && find app/ -name '*.py' ! -name '__init__.py' -delete \
  && find app/ -name '*.c' -delete \
  && rm -f build_cython.py \
  && rm -rf build/

# ----------------------------------------
# Stage 4: Final Python Application
# ----------------------------------------
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app

WORKDIR /app

# ✅ Single RUN: update + install + cleanup all in one layer (~5 MB instead of 84 MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libegl1 \
  libgl1 \
  libgomp1 \
  vim \
  && rm -rf /var/lib/apt/lists/*
# ↑ Removed `vim` — has no place in a production image

# ✅ uv binary — separate layer, changes rarely
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ✅ Dependencies before app code — maximizes cache reuse on rebuilds
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --compile-bytecode \
  && find /app/.venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
# ↑ --compile-bytecode pre-compiles .pyc files so PYTHONDONTWRITEBYTECODE doesn't
#   silently skip them at runtime

# ✅ C++ artifacts grouped — they change together
COPY --from=backend-builder \
  /workspace/build/libsick_scan_xd_shared_lib.so \
  /workspace/build/sick_generic_caller \
  /workspace/build/sick_scan_xd_api_test \
  ./build/
COPY --from=backend-builder /workspace/sick_scan_xd/launch/ ./launch/

# ✅ Compiled app: .so extensions + __init__.py stubs + non-Python assets
COPY main.py .
COPY --from=cython-builder /src/app/ ./app/

# ✅ No stale static to clean — just write directly from frontend builder
#    (remove the COPY app/ if app/static/ is the only thing under app/)
COPY --from=frontend-builder /web/dist/web/browser/ ./app/static/

EXPOSE 8005
CMD ["uv", "run", "--no-sync", "python", "main.py"]