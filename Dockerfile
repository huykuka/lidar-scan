# Multi-stage build for LiDAR Standalone Application

# Stage 1: Build Angular frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /app/web

# Copy package files for dependency installation
COPY web/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY web/ ./

# Build production frontend
RUN npm run build

# Stage 2: Python backend with built frontend
FROM python:3.12-slim

# Install system dependencies for Open3D and other requirements
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY app/ ./app/
COPY main.py .
COPY pytest.ini .

# Copy launch and build folders as-is
COPY launch/ ./launch/
COPY build/ ./build/

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/web/dist/web/browser ./app/static

# Create necessary directories
RUN mkdir -p config debug_data

# Expose port
EXPOSE 8005

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8005

# Run the application
CMD ["python", "main.py"]
