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
FROM node:24-slim AS frontend-builder
WORKDIR /web
# Copy package manifests first for caching
COPY web/package*.json ./
RUN npm ci
# Copy rest of frontend source and build
COPY web/ ./
RUN npm run build -- --configuration production

# ----------------------------------------
# Stage 3: Final Python Application
# ----------------------------------------
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (Build + Runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libgl1 \
  libglib2.0-0 \
  libgomp1 \
  libstdc++6 \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
  # Clean up only pycache
  find /usr/local/lib/python3.12/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Copy backend setup artifacts
COPY --from=backend-builder /workspace/build/libsick_scan_xd_shared_lib.so ./build/
COPY --from=backend-builder /workspace/build/sick_generic_caller ./build/
COPY --from=backend-builder /workspace/build/sick_scan_xd_api_test ./build/
COPY --from=backend-builder /workspace/sick_scan_xd/launch/ ./launch/

# Copy application files (This might include a stale local app/static directory)
COPY main.py .
COPY app/ ./app/
COPY scripts/ ./scripts/

# Clean any legacy local web builds that just got copied over, and fetch the fresh frontend build
RUN rm -rf ./app/static/*
COPY --from=frontend-builder /web/dist/web/browser/ ./app/static/

EXPOSE 8005

CMD [ "bash", "scripts/run.sh" ]
